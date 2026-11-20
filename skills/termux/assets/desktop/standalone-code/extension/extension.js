const { execFile } = require("node:child_process");
const { promisify } = require("node:util");
const vscode = require("vscode");

const run = promisify(execFile);
const hostPackage = "com.scisaga.tabletvscode";

async function activate(context) {
    const tag = process.env.TABLET_VSCODE_DOCK_TAG;
    const am = process.env.TABLET_VSCODE_ANDROID_AM;
    const token = process.env.TABLET_VSCODE_WINDOW_TOKEN;
    if (!am || !/^vscode-\d{1,2}$/.test(tag || "")) {
        return;
    }

    // The Termux app_process wrapper needs Android's loader environment.
    const androidEnv = { ...process.env };
    for (const key of ["LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT", "CLASSPATH"]) {
        delete androidEnv[key];
    }
    function intent(args) {
        return run(am, [...args, "--user", "0"], { env: androidEnv, timeout: 8000 });
    }

    async function newWindow() {
        if (/^[0-9a-f]{32}$/.test(token || "")) {
            try {
                const result = await intent([
                    "broadcast", "-a", hostPackage + ".NEW_WINDOW_REQUEST", "-p", hostPackage,
                    "--es", "document_tag", tag, "--es", "editor_token", token,
                ]);
                if (result.stdout.includes("Broadcast completed: result=-1")
                        || result.stdout.includes("Broadcast sent without waiting for result")) {
                    return;
                }
            } catch {
                // Avoid including the window token in the command failure message.
            }
            vscode.window.showErrorMessage("Could not open an Android VS Code window.");
            return;
        }
        try {
            const result = await intent([
                "start", "-a", hostPackage + ".NEW_WINDOW",
                "-n", hostPackage + "/com.termux.x11.CodeLauncher",
            ]);
            if (/\bError\b|Exception/.test(result.stdout + result.stderr)) {
                throw new Error((result.stderr || result.stdout).trim());
            }
        } catch (error) {
            vscode.window.showErrorMessage("Could not open an Android VS Code window. " + error.message);
        }
    }

    function publishWorkspace() {
        const title = (vscode.workspace.name || "").slice(0, 160);
        return intent([
            "broadcast", "-a", hostPackage + ".WINDOW_TITLE", "-p", hostPackage,
            "--es", "document_tag", tag, "--es", "title", title,
        ]).catch(error => console.warn("Could not update the Android VS Code window title", error.message));
    }

    context.subscriptions.push(vscode.commands.registerCommand("workbench.action.newWindow", newWindow));
    context.subscriptions.push(vscode.workspace.onDidChangeWorkspaceFolders(publishWorkspace));
    await publishWorkspace();
}

module.exports = { activate };
