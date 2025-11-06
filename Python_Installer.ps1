function Install-PythonFromMsStore {
    try {
        # Use winget to install Python from the Microsoft Store
        $process = Start-Process -FilePath "winget" -ArgumentList "install --id 9NRWMJP3717K --accept-package-agreements --accept-source-agreements" -PassThru -Wait
        if ($process.ExitCode -ne 0) {
            Write-Host "Python installation from Microsoft Store failed (exit code $($process.ExitCode))."
        } else {
            Write-Host "Python installation from Microsoft Store complete."
        }
    } catch {
        Write-Host "Failed to install Python from Microsoft Store: $_"
    }
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Host "Python is already installed: $(python --version 2>$null)"
} else {
    Write-Host "Python not found. Installing Python from Microsoft Store..."
    Install-PythonFromMsStore
}