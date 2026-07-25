# batch_install_docker.ps1 - Batch install Docker on 6 OpenStack VMs
# Proven workflow: upload script → install → verify (all 6 in parallel)
# Benchmark: ~8 min for 6 VMs (vs ~90 min manual first time)
# Usage: powershell -File batch_install_docker.ps1
# Prerequisites: deploy_vms.ps1 completed successfully

$ErrorActionPreference = "Continue"
$DOCKER_SKILL_DIR = "c:\obsidian\.trae\skills\docker"

# VM definitions: must match deploy_vms.ps1 output
# Update IPs after each deploy_vms.ps1 run by reading from OpenStack
$OPENSTACK_NODE = "10.0.10.13"
$OS_CMD = "source /etc/kolla/admin-openrc.sh && source /path/to/venv/bin/activate"

Write-Host "Fetching current VM IPs from OpenStack..." -ForegroundColor Cyan
$vmNames = @("test-ubuntu2204","test-debian12","test-almalinux9","test-rocky9","test-anolis23","test-openeuler24")
$vmConfig = @(
    @{Name="test-ubuntu2204";  User="ubuntu";    Type="debian";   Script="install_docker_debian.sh"}
    @{Name="test-debian12";    User="debian";    Type="debian";   Script="install_docker_debian.sh"}
    @{Name="test-almalinux9";  User="almalinux"; Type="rhel";     Script="install_docker_rhel.sh";    Args="almalinux 9"}
    @{Name="test-rocky9";      User="rocky";     Type="rhel";     Script="install_docker_rhel.sh";    Args="rocky 9"}
    @{Name="test-anolis23";    User="root";      Type="rhel";     Script="install_docker_rhel.sh";    Args="anolis 9"}
    @{Name="test-openeuler24"; User="root";      Type="openeuler";Script="install_docker_openeuler.sh"}
)

# Auto-detect IPs from OpenStack
foreach ($vm in $vmConfig) {
    $addrRaw = ssh root@$OPENSTACK_NODE "$OS_CMD && openstack server show $($vm.Name) -f value -c addresses" 2>$null
    $ip = ($addrRaw -split "=" | Select-Object -Last 1).Trim()
    $vm.IP = $ip
    Write-Host "  $($vm.Name) -> $ip"
}

Write-Host "`n========== Installing Docker on all VMs ==========" -ForegroundColor Cyan

# Upload scripts in parallel
Write-Host "Uploading install scripts..."
$jobs = @()
foreach ($vm in $vmConfig) {
    $scriptPath = "$DOCKER_SKILL_DIR\scripts\$($vm.Script)"
    $remotePath = "/tmp/install_docker.sh"
    $jobs += Start-Job -ScriptBlock {
        param($scriptPath, $ip, $user)
        scp -o StrictHostKeyChecking=no $scriptPath "${user}@${ip}:/tmp/install_docker.sh" 2>&1
    } -ArgumentList $scriptPath, $vm.IP, $vm.User
}
$jobs | Wait-Job | Out-Null
$jobs | Remove-Job
Write-Host "All scripts uploaded."

# Install in parallel
Write-Host "`nInstalling Docker (parallel)..."
$jobs = @()
foreach ($vm in $vmConfig) {
    $jobs += Start-Job -ScriptBlock {
        param($ip, $user, $args2, $type)
        $sshTarget = "${user}@${ip}"
        if ($type -eq "debian") {
            $cmd = "sudo bash /tmp/install_docker.sh"
        } elseif ($type -eq "rhel") {
            $cmd = "sudo bash /tmp/install_docker.sh $args2"
        } else {
            $cmd = "bash /tmp/install_docker.sh"
        }
        $output = ssh -o StrictHostKeyChecking=no $sshTarget $cmd 2>&1
        return @{Name=$sshTarget; Output=$output}
    } -ArgumentList $vm.IP, $vm.User, $vm.Args, $vm.Type
}

# Wait and collect results
$installResults = @()
foreach ($job in $jobs) {
    $result = $job | Wait-Job | Receive-Job
    $installResults += $result
    Write-Host "  $($result.Name) - install complete"
}
$jobs | Remove-Job

Write-Host "`n========== Verifying Docker ==========" -ForegroundColor Cyan
$results = @()
foreach ($vm in $vmConfig) {
    $sshUser = $vm.User
    $ver = ssh -o StrictHostKeyChecking=no "${sshUser}@$($vm.IP)" "docker --version 2>/dev/null; systemctl is-active docker 2>/dev/null; docker compose version 2>/dev/null" 2>$null
    $lines = ($ver -split "`n" | Where-Object { $_.Trim() })
    $dockerVer = if ($lines.Count -ge 1) { $lines[0].Trim() } else { "N/A" }
    $active = if ($lines.Count -ge 2) { $lines[1].Trim() } else { "N/A" }
    $composeVer = if ($lines.Count -ge 3) { $lines[2].Trim() } else { "N/A" }

    $color = if ($active -eq "active") { "Green" } else { "Red" }
    Write-Host "  $($vm.Name) ($($vm.IP))" -ForegroundColor $color
    Write-Host "    Docker: $dockerVer | Active: $active | Compose: $composeVer"

    $results += [PSCustomObject]@{
        Name=$vm.Name; IP=$vm.IP; Docker=$dockerVer; Active=$active; Compose=$composeVer
    }
}

Write-Host "`n========== Summary ==========" -ForegroundColor Cyan
$results | Format-Table -AutoSize

$okCount = ($results | Where-Object { $_.Active -eq "active" }).Count
Write-Host "`n$okCount / $($vmConfig.Count) VMs have Docker running" -ForegroundColor $(if ($okCount -eq $vmConfig.Count) {"Green"} else {"Yellow"})

if ($okCount -eq $vmConfig.Count) {
    Write-Host "`nAll Docker installations complete!" -ForegroundColor Green
}
