import importlib
import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
LOADER = importlib.machinery.SourceFileLoader("agent_box_launcher", str(ROOT / "bin/agent-box"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
launcher = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = launcher
LOADER.exec_module(launcher)
process = importlib.import_module("_lib")


class FakeDocker:
    def __init__(self, container=None):
        self.container = container
        self.commands = []

    def inspect(self, kind, name):
        if kind == "container":
            return self.container
        return None

    def run(self, args, **kwargs):
        self.commands.append(args)
        if args[0:2] == ["rm", "-f"]:
            self.container = None
        elif args[0] == "create":
            labels = {
                value.split("=", 1)[0]: value.split("=", 1)[1]
                for index, value in enumerate(args)
                if index and args[index - 1] == "--label"
            }
            self.container = {
                "Config": {"Labels": labels},
                "State": {"Running": False},
                "NetworkSettings": {"Networks": {}},
            }
        elif args[0] == "start":
            self.container["State"]["Running"] = True
        elif args[0:2] == ["network", "connect"]:
            self.container["NetworkSettings"]["Networks"][args[2]] = {}

        return subprocess.CompletedProcess(args, 0, "", "")


def agent_container(workspace, source="source", running=False):
    return {
        "Config": {
            "Labels": {
                f"{launcher.LABEL}.managed": "true",
                f"{launcher.LABEL}.role": "agent",
                f"{launcher.LABEL}.source": source,
                f"{launcher.LABEL}.spec": "2",
                f"{launcher.LABEL}.workspace": str(workspace),
            }
        },
        "State": {"Running": running},
    }


class AgentLifecycleTest(TestCase):
    def test_starts_matching_stopped_container_without_recreating_it(self):
        workspace = Path("/workspace").resolve()
        docker = FakeDocker(agent_container(workspace))
        with patch.object(launcher, "ensure_image", return_value="source"):
            name = launcher.ensure_agent(docker, workspace)

        self.assertEqual(name, launcher.project_name(workspace))
        self.assertEqual(docker.commands, [["start", name]])

    def test_recreates_stale_container_and_preserves_home_volume(self):
        workspace = Path("/workspace").resolve()
        name = launcher.project_name(workspace)
        docker = FakeDocker(agent_container(workspace, source="old", running=True))
        with patch.object(launcher, "ensure_image", return_value="new"):
            launcher.ensure_agent(docker, workspace)

        self.assertEqual(docker.commands[0], ["rm", "-f", name])
        create = next(command for command in docker.commands if command[0] == "create")
        self.assertIn(f"type=volume,source={name}-home,target=/home/node", create)
        self.assertNotIn("volume", docker.commands[-1])
        self.assertEqual(docker.commands[-1], ["start", name])

    def test_passes_options_to_agent_commands_without_separator(self):
        with patch.object(sys, "argv", ["agent-box", "claude", "-p", "hello"]):
            args = launcher.parse_args()

        self.assertEqual(args.command, "claude")
        self.assertEqual(args.args, ["-p", "hello"])

    def test_passes_shell_options_without_separator(self):
        with patch.object(sys, "argv", ["agent-box", "shell", "-c", "pwd"]):
            args = launcher.parse_args()

        self.assertEqual(args.args, ["-c", "pwd"])


class GatewayLifecycleTest(TestCase):
    def test_recreates_gateway_when_network_config_changes(self):
        docker = FakeDocker(
            {
                "Config": {
                    "Labels": {
                        f"{launcher.LABEL}.managed": "true",
                        f"{launcher.LABEL}.role": "gateway",
                        f"{launcher.LABEL}.source": "source",
                        f"{launcher.LABEL}.network": "old",
                        f"{launcher.LABEL}.spec": "1",
                    }
                },
                "State": {"Running": True},
                "NetworkSettings": {"Networks": {launcher.NETWORK: {}, "bridge": {}}},
            }
        )
        network = launcher.NetworkConfig(["registry.npmjs.org"], "new")
        with patch.object(launcher, "ensure_image", return_value="source"):
            launcher.ensure_gateway(docker, network)

        self.assertEqual(docker.commands[0], ["rm", "-f", launcher.GATEWAY_CONTAINER])
        create = next(command for command in docker.commands if command[0] == "create")
        self.assertIn(f"{launcher.LABEL}.network=new", create)
        self.assertEqual(docker.commands[-1], ["start", launcher.GATEWAY_CONTAINER])


class ProcessTest(TestCase):
    def test_returns_captured_output(self):
        result = process.output([sys.executable, "-c", "print('ready')"])

        self.assertEqual(result, "ready")

    def test_reports_process_error(self):
        with self.assertRaisesRegex(SystemExit, "broken"):
            process.run(
                [sys.executable, "-c", "import sys; sys.stderr.write('broken'); exit(2)"],
                capture=True,
            )


if __name__ == "__main__":
    main()
