#include <windows.h>

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {
    // Get the current directory
    CHAR currentPath[MAX_PATH];
    CHAR mainExePath[MAX_PATH];
    CHAR* lastSlash;
    
    GetModuleFileNameA(NULL, currentPath, MAX_PATH);
    
    lastSlash = strrchr(currentPath, '\\');
    if (lastSlash) {
        *lastSlash = '\0';
    }
    
    // Construct path to main.exe
    lstrcpyA(mainExePath, currentPath);
    lstrcatA(mainExePath, "\\assets\\main.dist\\main.exe");
    
    // Execute main.exe
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    
    ZeroMemory(&si, sizeof(si));
    ZeroMemory(&pi, sizeof(pi));
    
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_NORMAL;
    
    if (CreateProcessA(
        mainExePath,
        NULL,
        NULL,
        NULL,
        FALSE,
        0,
        NULL,
        NULL,
        &si,
        &pi
    )) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
    
    return 0;
}