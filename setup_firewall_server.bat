@echo off
setlocal

echo [ProspEl] Adding firewall rule for frontend TCP 5173...
netsh advfirewall firewall add rule name="ProspEl Frontend 5173" dir=in action=allow protocol=TCP localport=5173 profile=private

echo [ProspEl] Optional backend direct access rule TCP 8000...
netsh advfirewall firewall add rule name="ProspEl Backend 8000 (Optional)" dir=in action=allow protocol=TCP localport=8000 profile=private

echo [ProspEl] Rules created.
pause
