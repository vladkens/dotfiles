function vercel --description 'Run vercel with VERCEL_TOKEN from the Keychain'
    kc run VERCEL_TOKEN -- vercel $argv
end
