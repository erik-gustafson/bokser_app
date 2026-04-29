param(
    [string]$Action = "up",
    [switch]$Build,
    [switch]$Detached,
    [switch]$Logs,
    [switch]$Down,
    [switch]$Migrate
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$DockerDir = Join-Path $ProjectRoot "docker"
$ComposeFile = Join-Path $DockerDir "docker-compose.yml"
$DevComposeFile = Join-Path $DockerDir "docker-compose.dev.yml"
$EnvFile = Join-Path $DockerDir ".env"

if (-not (Test-Path $ComposeFile)) {
    throw "Missing compose file: $ComposeFile"
}

if (-not (Test-Path $DevComposeFile)) {
    throw "Missing dev compose file: $DevComposeFile"
}

if (-not (Test-Path $EnvFile)) {
    throw "Missing env file: $EnvFile"
}

Set-Location $ProjectRoot

$ComposeArgs = @(
    "compose",
    "--env-file", $EnvFile,
    "-f", $ComposeFile,
    "-f", $DevComposeFile
)

if ($Down) {
    docker @ComposeArgs down
    exit $LASTEXITCODE
}

if ($Migrate) {
    docker @ComposeArgs run --rm migrate
    exit $LASTEXITCODE
}

if ($Logs) {
    docker @ComposeArgs logs -f
    exit $LASTEXITCODE
}

switch ($Action.ToLower()) {
    "up" {
        $UpArgs = @("up")

        if ($Build) {
            $UpArgs += "--build"
        }

        if ($Detached) {
            $UpArgs += "-d"
        }

        docker @ComposeArgs @UpArgs
    }

    "build" {
        docker @ComposeArgs build
    }

    "restart" {
        docker @ComposeArgs restart
    }

    "ps" {
        docker @ComposeArgs ps
    }

    "config" {
        docker @ComposeArgs config
    }

    default {
        throw "Unknown action '$Action'. Use: up, build, restart, ps, config, or switches -Down, -Logs, -Migrate."
    }
}