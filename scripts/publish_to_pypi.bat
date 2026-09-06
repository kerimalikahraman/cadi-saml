@echo off
echo ========================================================
echo Publishing cadi_saml v0.4.0 to PyPI
echo ========================================================

cd /d "%~dp0\.."

echo Building source distribution and wheel...
python -m build

echo.
echo Checking package integrity with twine...
twine check dist/*

echo.
echo Uploading to PyPI...
echo (When prompted, enter username: __token__ and password: your_pypi_api_token)
twine upload dist/*

echo.
echo Done! Verify by running: pip install --upgrade cadi_saml
pause
