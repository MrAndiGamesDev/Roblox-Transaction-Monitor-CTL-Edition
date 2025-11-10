function Install-PythonFromStore {
    try {
        $wingetArgs = @(
            'install',
            '--id',
            '--version',
            '3.13',
            '--accept-package-agreements',
            '--accept-source-agreements'
        )
        $process = Start-Process -FilePath 'winget' -ArgumentList $wingetArgs -NoNewWindow -Wait -PassThru
        if ($process.ExitCode -eq 0) {
            Write-Host 'Python 3.13 installation from Microsoft Store complete.'
        } else {
            Write-Warning "Python 3.13 installation failed (exit code $($process.ExitCode))."
        }
    } catch {
        Write-Error "Failed to install Python 3.13 from Microsoft Store: $_"
    }
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    $currentVersion = python --version 2>$null
    if ($currentVersion -match '3\.13') {
        Write-Host "Python 3.13 is already installed: $currentVersion"
    } else {
        Write-Host "Python is installed but not version 3.13: $currentVersion"
        Write-Host 'Installing Python 3.13 from Microsoft Store...'
        Install-PythonFromStore
    }
} else {
    Write-Host 'Python not found. Installing Python 3.13 from Microsoft Store...'
    Install-PythonFromStore
}