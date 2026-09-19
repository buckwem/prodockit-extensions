---
icon: lucide/book-open
---

{{ heading_counter_reset(page) }}

<!--
Copyright (c) 2025-2026 Mark Buckwell and contributors
SPDX-License-Identifier: MIT
-->

# Build site manually

This section explains how to \index{Tasks!Install manually} by preparing a
computer and a project. It covers macOS, Windows, and Linux (Ubuntu). The
instructions cover a new project from the Prodockit template (Path 1) or an
existing Prodockit-ready repository (Path 2). To add Prodockit to a plain
Zensical site, use [Adopt prodockit](getting-started.md) instead.

!!! warning "Manual installation is not recommended"
    Manual installation is a long process with many opportunities for
    problems, including failed downloads, partial installations, and mistakes
    in commands. This is why Prodockit provides Bootstrap and Adopt: they
    automate most of the work and verify each stage. You may still prefer to
    install everything yourself, and this section documents that route. It
    also demonstrates why producing a PDF containing Mermaid diagrams and
    MathJax notation is not simple: the process depends on several Python,
    system, browser, font, and Node.js components working together.

Work through the steps in order. Where a tool is already installed, still
run the check shown for it before continuing.

## Manual installation stages

Each stage groups a related part of the installation. Complete its numbered
steps before moving to the next stage. Use only the instructions for your
operating system{% if is_surrey %} and use Surrey GitLab for your coursework{% else %}
and chosen Git host; you do not need both GitHub and GitLab{% endif %}.
Skip tools that already pass the checks, but do not skip verification.

For existing work, keep its content, custom settings and publishing workflow.
Make changes on a new branch or in a separate clone, and save any uncommitted
work first: creating a branch alone does not make a backup of it.

### Stage 1 — Prepare the computer

Install the shared tools and identify the Git account that will own the work.

/// steps

//// step | Prepare Python and the setup environment

Complete [section 3.1, Prepare Python and its
environment](installation.md#installation-preparation) first. It installs
Python 3.14, creates the setup `.venv` in your parent repositories directory,
activates it, and verifies that the shell is using the intended interpreter.

[Open section 3.1 to prepare your environment](installation.md#installation-preparation){ .md-button .md-button--primary target="_blank" }

Remain in that parent directory with the setup environment active for the
machine and repository preparation below. The instructions explicitly say
when to enter the project, deactivate this setup environment, and create the
project's own `.venv`.

////

//// step | Install Visual Studio Code **Optional**{: .bg-green}

[Visual Studio Code](https://code.visualstudio.com){target="_blank"} (VS Code) is the editor we have chosen for developing the documentation using Zensical. You can use other editors, but the availability of many plugins in Visual Studio Code will help you edit your documentation more efficiently.

Skip this step if you already have an editor you prefer. An editor is useful
for reviewing files, but VS Code is not required to build the website or PDF.

Start with installing [Visual Studio Code](https://code.visualstudio.com){target="_blank"}. Instructions for macOS, Windows, and Linux (Ubuntu/Debian) are below.

=== ":material-apple: macOS"

    1. Open the **Terminal** application.
    1. You are likely to already have [Homebrew](https://brew.sh){target="_blank"} installed, but if not, follow the instructions on [brew.sh](https://brew.sh){target="_blank"} to install it.  **Close and reopen your Terminal after installing it.** As the installer adds `brew` to your `PATH`, and a session that was already open won't pick that up.

    1. Use the Homebrew package manager to install Visual Studio Code in your Terminal:
        ``` bash
        brew update
        brew install --cask visual-studio-code
        ```

=== ":fontawesome-brands-windows: Windows"

    1. Download the VS Code User setup for Windows from the [official website](https://code.visualstudio.com/download){target="_blank"}.
    2. Run the installer, `VSCodeUserSetup-{version}.exe`. By default the User setup installs Visual Studio Code to your user profile directory. You can change the install location if you want to install it for all users.

=== ":material-linux: Linux (Ubuntu)"

    1. Download the `.deb` package from the [official website](https://code.visualstudio.com/).
    2. Open a terminal and navigate to the directory where you downloaded the `.deb` package.
    3. Run the following command to install Visual Studio Code:
        ``` bash
        sudo apt install ./<file>.deb
        ```
    Replace `<file>` with the name of the downloaded `.deb` file.

    Further installation instructions are available on the [Visual Studio Code website](https://code.visualstudio.com/docs/setup/linux){target="_blank"}.


////

//// step | Install Git

\index{<a href="https://git-scm.com/" target="_blank">Git</a>} is a version control system that enables you to track changes to your code and collaborate with others. You will be using Git to manage your documentation website and push your changes to your {% if is_surrey %}[**Surrey GitLab**](https://gitlab.surrey.ac.uk){target="_blank" rel="noopener"}{% else %}**GitLab** or **GitHub**{% endif %} repository.

Install and configure Git next. The instructions below work with
{% if is_surrey %}Surrey GitLab.{% else %}both *GitLab* and *GitHub*.{% endif %}

Start by installing Git and configuring it for Visual Studio Code. The instructions below are for macOS, Windows, and Linux (Ubuntu/Debian).

1. As a start, you need to install the `git` command. Follow the instructions below to install or update `git` to the latest stable version.

    === ":material-apple: macOS"

        Use the Homebrew package manager to install or update `git` to the latest stable version:

        ``` bash
        brew install git
        ```

    === ":fontawesome-brands-windows: Windows"

        Open up a **PowerShell** Administrator window and install `git` using the command, or you can download and install the official git installer from [git-scm.com](https://git-scm.com/download/win){target="_blank"}.

        ``` PowerShell
        winget install Git.Git
        ```

        If you just require an updated version of `git`, you can run the following command in **PowerShell**:

        ``` PowerShell
        winget upgrade Git.Git
        ```

        **Close down PowerShell** and reopen it after installing or updating `git` to ensure that the new version is available in your `PATH`. Check the version of `git` installed by running the following command in **PowerShell**:

        ``` PowerShell
        git --version
        ```

    === ":material-linux: Linux (Ubuntu)"

        Open a terminal and run the following command to install or update `git` to the latest stable version:

        ``` bash
        sudo apt update
        sudo apt install git
        ```

////

//// step | Register with the Git hosting service

{% if is_surrey %}
Use your university account on [Surrey GitLab](https://gitlab.surrey.ac.uk){target="_blank" rel="noopener"} for coursework. Select **Surrey Login** and sign in with your university credentials. If you have already signed in, skip this step.
{% else %}
Register for an account on the public [**GitLab**](https://gitlab.com){target="_blank"} or [**GitHub**](https://github.com){target="_blank"} cloud instance you will use. If you have already registered, you can skip this step.
{% endif %}

////

///

### Stage 2 — Configure secure Git access

Create SSH keys, protect them, and confirm that the hosting service accepts
them before downloading a project.

If SSH already works for your chosen host, skip to the connection check at the
end of this stage. If your existing project uses authenticated HTTPS, keep
that arrangement and use its HTTPS clone URL in Stage 3 instead. Create and
configure keys only for the host you use; never overwrite an existing key.

/// steps

//// step | Generate the SSH keys

{% if is_surrey %}
Configure SSH keys to authenticate with your GitLab account. Your
coursework lives on the University of Surrey's GitLab, so that is the only
account you need a key for here.
{% else %}
Configure SSH keys to authenticate with your GitLab or GitHub
account.
{% endif %}

1. Follow the instructions below to generate a new \index{Git!ssh key pair} and add it to your account. It's best practice to use a modern, secure `ed25519` key.

    === ":material-apple: macOS"

        1. Open the **Terminal** application.
{% if is_surrey %}
        2. Generate the key. Only the email address needs changing - the rest of the command is complete as written:

            ``` bash
            ssh-keygen -t ed25519 -C "your.email@example.com" -f ~/.ssh/id_ed25519_gitlab
            ```

        3. When prompted, type a strong passphrase.
{% else %}
        2. Generate the key for **GitHub**. Only the email address needs changing - the rest of the command is complete as written:

            ``` bash
            ssh-keygen -t ed25519 -C "your.github.email@example.com" -f ~/.ssh/id_ed25519_github
            ```

        3. Then generate a **separate** key for **GitLab**:

            ``` bash
            ssh-keygen -t ed25519 -C "your.gitlab.email@example.com" -f ~/.ssh/id_ed25519_gitlab
            ```

        4. When prompted, type a strong passphrase. You are asked once per key, so this happens twice.
{% endif %}

    === ":fontawesome-brands-windows: Windows"

        1. Open the **PowerShell** application.
        2. Create the `.ssh` folder, if it doesn't already exist:

            ``` powershell
            mkdir $env:USERPROFILE\.ssh -Force
            ```

{% if is_surrey %}
        3. Generate the key. Only the email address needs changing - the rest of the command is complete as written:

            ``` powershell
            ssh-keygen -t ed25519 -C "your.email@example.com" -f $env:USERPROFILE\.ssh\id_ed25519_gitlab
            ```

        4. When prompted, type a strong passphrase.
{% else %}
        3. Generate the key for **GitHub**. Only the email address needs changing - the rest of the command is complete as written:

            ``` powershell
            ssh-keygen -t ed25519 -C "your.github.email@example.com" -f $env:USERPROFILE\.ssh\id_ed25519_github
            ```

        4. Then generate a **separate** key for **GitLab**:

            ``` powershell
            ssh-keygen -t ed25519 -C "your.gitlab.email@example.com" -f $env:USERPROFILE\.ssh\id_ed25519_gitlab
            ```

        5. When prompted, type a strong passphrase. You are asked once per key, so this happens twice.
{% endif %}

    === ":material-linux: Linux (Ubuntu)"

        1. Open the **Terminal** application.
{% if is_surrey %}
        2. Generate the key. Only the email address needs changing - the rest of the command is complete as written:

            ``` bash
            ssh-keygen -t ed25519 -C "your.email@example.com" -f ~/.ssh/id_ed25519_gitlab
            ```

        3. When prompted, type a strong passphrase.
{% else %}
        2. Generate the key for **GitHub**. Only the email address needs changing - the rest of the command is complete as written:

            ``` bash
            ssh-keygen -t ed25519 -C "your.github.email@example.com" -f ~/.ssh/id_ed25519_github
            ```

        3. Then generate a **separate** key for **GitLab**:

            ``` bash
            ssh-keygen -t ed25519 -C "your.gitlab.email@example.com" -f ~/.ssh/id_ed25519_gitlab
            ```

        4. When prompted, type a strong passphrase. You are asked once per key, so this happens twice.
{% endif %}


{% if not is_surrey %}
    !!! note "`gitxxx` in the steps that follow"
        You now have two key files, `id_ed25519_github` and
        `id_ed25519_gitlab`. The remaining steps are written once, with
        `gitxxx` standing for whichever of the two you are working on -
        so run them twice, substituting `github` and then `gitlab`.
{% endif %}

////

//// step | Configure SSH to use the keys

1. Configure the SSH config file to use the correct key for your chosen service.
    Keep existing settings. Add only the missing host block below; do not
    replace the whole file or duplicate a host that is already configured.

    === ":material-apple: macOS"

        Open the file in your preferred text editor (create it if it does not
        exist) - for example with `nano`:

        ```bash
        nano ~/.ssh/config
        ```

        Paste in the configuration below, then save and close (`Ctrl+O` to save, `Ctrl+X` to exit, in nano).

    === ":fontawesome-brands-windows: Windows"

        Create the file from PowerShell first, then open it - creating it directly inside an editor risks Notepad naming it `config.txt` instead of `config`:

        ``` powershell
        if (!(Test-Path $env:USERPROFILE\.ssh\config)) {
            New-Item -ItemType File -Path $env:USERPROFILE\.ssh\config
        }
        code $env:USERPROFILE\.ssh\config
        ```

        (Use `notepad` in place of `code` if you'd rather not use VS Code.) Paste in the configuration below, then save.

        !!! warning "The file must be called `config`, with no extension"
            Notepad silently appends `.txt` unless you prevent it, and Windows hides known extensions in File Explorer, so `config.txt` looks identical to `config`. SSH reads only a file named exactly `config` - a misnamed one is ignored entirely, and `git clone` falls back to asking for a password that will never be accepted. Creating the file with `New-Item` first avoids this. To check, and fix it if needed:

            ``` powershell
            Get-ChildItem $env:USERPROFILE\.ssh
            Rename-Item $env:USERPROFILE\.ssh\config.txt config   # only if the first command lists config.txt
            ```

    === ":material-linux: Linux (Ubuntu)"

        Open the file in your preferred text editor (create it if it does not
        exist) - for example with `nano`:

        ```bash
        nano ~/.ssh/config
        ```

        Paste in the configuration below, then save and close (`Ctrl+O` to save, `Ctrl+X` to exit, in nano).


    The configuration to paste in:

{% if is_surrey %}
    ```text
    # GitLab (University of Surrey)
    Host gitlab.surrey.ac.uk
        HostName gitlab.surrey.ac.uk
        User git
        IdentityFile ~/.ssh/id_ed25519_gitlab
        AddKeysToAgent yes

    ```
{% else %}
    ```text
    # GitLab
    Host gitlab.com
        HostName gitlab.com
        User git
        IdentityFile ~/.ssh/id_ed25519_gitlab
        AddKeysToAgent yes

    # GitHub
    Host github.com
        HostName github.com
        User git
        IdentityFile ~/.ssh/id_ed25519_github
        AddKeysToAgent yes
    ```
{% endif %}

    Make sure to replace the paths with the correct paths to your SSH keys if you used different names or locations. `AddKeysToAgent yes` is what makes the key-loading step below self-healing - without it, the key you add to the agent today is gone the next time the agent restarts (a reboot, a logout, on some setups just time), and SSH fails with a permission error that looks like a rejected key rather than a missing one, since the *public* half still authenticates fine and only the signing step - which needs the private half - actually fails.

    !!! tip "On macOS, add one more line"
        Add `UseKeychain yes` too, in each `Host` block above, so macOS can supply the passphrase from your login keychain instead of asking every time - paired with `--apple-use-keychain` on `ssh-add` below. This directive is Apple-specific: **don't** add it on Windows or Linux, where it isn't recognised and breaks every `ssh` command that reads this file with `Bad configuration option: usekeychain`.

{% if not is_surrey %}
    !!! tip
        Separate keys per account are safer, but if you reuse one, add its public key to each account separately in [Integrate Visual Studio Code with Git](#integrate-visual-studio-code-with-git) below.
{% endif %}

////

//// step | Protect the SSH configuration and private keys

1. Set the correct permissions for the SSH config file and the private key(s) to ensure they're secure. If you are using macOS or Linux, run the following commands in your terminal{% if not is_surrey %}, substituting `gitxxx` and paths to your SSH keys if you used different names or locations{% endif %}:

{% if is_surrey %}
    ```bash
    chmod 600 ~/.ssh/config
    chmod 600 ~/.ssh/id_ed25519_gitlab
    ```
{% else %}
    ```bash
    chmod 600 ~/.ssh/config
    chmod 600 ~/.ssh/id_ed25519_gitxxx
    ```
{% endif %}

    Windows handles permissions differently and are normally set to only allow access to the user, but ensure that the private key(s) aren't accessible to other users.

////

//// step | Load the private keys into the SSH agent

1. You've set a passphrase for the SSH keys, so you'll need to enter it every time you use a key. To avoid this, you can use an SSH agent to cache your passphrase. Follow the instructions below to start the SSH agent and add your keys.

    === ":material-apple: macOS"

        1. macOS normally starts an SSH agent for you automatically. Add your SSH private key{% if not is_surrey %}s{% endif %} to it{% if not is_surrey %}, substituting `gitxxx` with either `github` or `gitlab` depending on which service you are adding the key for{% endif %} - `--apple-use-keychain` stores the passphrase in your login keychain, so the key survives a reboot instead of silently dropping out of the agent:

{% if is_surrey %}
            ``` bash
            ssh-add --apple-use-keychain ~/.ssh/id_ed25519_gitlab
            ```
{% else %}
            ``` bash
            ssh-add --apple-use-keychain ~/.ssh/id_ed25519_gitxxx
            ```
{% endif %}

            If this fails with an error about not being able to connect to the agent, start one first, then repeat the command above:

            ``` bash
            eval "$(ssh-agent -s)"
            ```

    === ":fontawesome-brands-windows: Windows"

        1. Set the SSH agent to start automatically with Windows, and then start it. Run these in a PowerShell window opened **as Administrator** (right-click the Start menu, or search for PowerShell, then select **Run as administrator**):

            ``` powershell
            Set-Service -Name ssh-agent -StartupType Automatic
            Start-Service ssh-agent
            ```

            !!! warning "Run in that order, in an Administrator window"
                Windows ships this service **disabled**, so `Set-Service` has to take it out of that state before `Start-Service` has anything it's allowed to start - reversed, the first command fails with `Cannot start service ssh-agent`. Both commands also need elevation: an ordinary window fails with `Access is denied`, which then makes the second command fail too, for the same underlying reason.

                An Administrator PowerShell opens in `C:\WINDOWS\system32` (an ordinary one opens in `C:\Users\yourname`), and its title bar says *Administrator*.

            Check it worked before moving on:

            ``` powershell
            Get-Service ssh-agent
            ```

            The **Status** column should read `Running`. If it still says `Stopped`, confirm the PowerShell window really is running as Administrator - the title bar says *Administrator* when it is.
        2. Back in your normal (non-administrator) PowerShell window, add your SSH private key{% if not is_surrey %}s{% endif %} to the agent{% if not is_surrey %}, substituting `gitxxx` with either `github` or `gitlab` depending on which service you are adding the key for{% endif %}:

{% if is_surrey %}
            ``` powershell
            ssh-add $env:USERPROFILE\.ssh\id_ed25519_gitlab
            ```
{% else %}
            ``` powershell
            ssh-add $env:USERPROFILE\.ssh\id_ed25519_gitxxx
            ```
{% endif %}

    === ":material-linux: Linux (Ubuntu)"

        1. Add your SSH private key{% if not is_surrey %}s{% endif %} to the running SSH agent{% if not is_surrey %}, substituting `gitxxx` with either `github` or `gitlab` depending on which service you are adding the key for{% endif %}:

{% if is_surrey %}
            ``` bash
            ssh-add ~/.ssh/id_ed25519_gitlab
            ```
{% else %}
            ``` bash
            ssh-add ~/.ssh/id_ed25519_gitxxx
            ```
{% endif %}

            Unlike macOS, Linux doesn't always start an SSH agent automatically. If the command above fails with an error about not being able to connect to the agent, start one first, then repeat the command above:

            ``` bash
            eval "$(ssh-agent -s)"
            ```

////

//// step | Copy the public keys

1. Display your **public** key, so you can copy it - the next section needs it pasted into your {% if is_surrey %}GitLab account{% else %}GitLab and GitHub accounts{% endif %}. Only the public key goes there; never paste the private one (the file with no `.pub` extension).

    === ":material-apple: macOS"

{% if is_surrey %}
        ``` bash
        cat ~/.ssh/id_ed25519_gitlab.pub
        ```
{% else %}
        ``` bash
        cat ~/.ssh/id_ed25519_gitxxx.pub
        ```
{% endif %}

    === ":fontawesome-brands-windows: Windows"

{% if is_surrey %}
        ``` powershell
        Get-Content $env:USERPROFILE\.ssh\id_ed25519_gitlab.pub
        ```
{% else %}
        ``` powershell
        Get-Content $env:USERPROFILE\.ssh\id_ed25519_gitxxx.pub
        ```
{% endif %}

    === ":material-linux: Linux (Ubuntu)"

{% if is_surrey %}
        ``` bash
        cat ~/.ssh/id_ed25519_gitlab.pub
        ```
{% else %}
        ``` bash
        cat ~/.ssh/id_ed25519_gitxxx.pub
        ```
{% endif %}


    {% if is_surrey %}Select the entire line it prints - starting with `ssh-ed25519` and ending with the email address you gave it - and copy it.{% else %}Substitute `gitxxx` as before, and run it once for each key you generated. Select the entire line it prints - starting with `ssh-ed25519` and ending with the email address you gave it - and copy it.{% endif %}

////

//// step | Add the public {% if is_surrey %}key to Surrey GitLab{% else %}keys to GitLab or GitHub{% endif %}

<span id="integrate-visual-studio-code-with-git"></span>

Add each public key to its hosting account, test the connection, and then let
Visual Studio Code use the same Git installation.

1. Now that you've generated your keys and finished the configuration, add {% if is_surrey %}it to your GitLab account{% else %}them to your GitHub and GitLab accounts{% endif %} using the instructions below.

{% if is_surrey %}
    === ":fontawesome-brands-gitlab: Surrey GitLab"

        1. Open [Surrey GitLab](https://gitlab.surrey.ac.uk){target="_blank" rel="noopener"}, select
           **Surrey Login**, and sign in with your university credentials.
{% else %}
    === ":fontawesome-brands-gitlab: GitLab"

        1. Log in to your **GitLab** account in a web browser.
{% endif %}
        2. In the top-right corner, click on your **profile avatar** and select **Edit profile**.
        3. On the left-hand sidebar, select **Access > SSH Keys**.
        4. Click **Add new key**{: .bg-blue} and fill out the following details:
            * **Title:** Give it a clear name (e.g., VS Code Extension).
            * **Key:** Paste the contents of your public SSH key file (e.g., `~/.ssh/id_ed25519_gitlab.pub`).
            * **Expiration date:** GitLab fills this in for you, one year ahead, and
              will not let you leave it empty. Set it well into the future - the end
              of your course or project, say - or you will be locked out mid-way
              through and have to generate and register a new key.
        5. Click **Add key**{: .bg-blue} to save the key.

        !!! warning "An expired key fails confusingly"
            When the date passes, `git push` and `git pull` stop working with a
            permission error that looks like a misconfigured key rather than an
            expired one. If pushing suddenly fails having worked for months, check
            this date first.
{% if not is_surrey %}
    === ":fontawesome-brands-github: GitHub"

        1. Log in to your **GitHub** account in a web browser.
        2. In the top-right corner, click on your **profile avatar** and select **Settings**.
        3. On the left-hand sidebar, select **SSH and GPG keys**.
        4. Click **New SSH key**{: .bg-green} and fill out the following details:
            * **Title:** Give it a clear name (e.g., VS Code Extension).
            * **Key:** Paste the contents of your public SSH key file (e.g., `~/.ssh/id_ed25519_github.pub`).
        5. Click **Add SSH key**{: .bg-green} to save the key.

        !!! note "No expiry date to set here"
            Unlike GitLab, GitHub SSH keys have no expiration field - the key
            stays valid until you delete it, so there is nothing to set.
{% endif %}

////

//// step | Test the SSH connection

{% if is_surrey %}
1. Test the SSH connection to GitLab to ensure that the key is working correctly. Run the following command in your terminal:

    ```bash
    ssh -T git@gitlab.surrey.ac.uk
    ```

    If successful, you will see a greeting like:

    ```text
    Welcome to GitLab, @username!
    ```
{% else %}
1. Test the SSH connection to GitHub and GitLab to ensure that the keys are working correctly. Run the following commands in your terminal:

    ```bash
    ssh -T git@gitxxx.com
    ```

    If successful, you will see greetings like:

    ```text
    Hi username! You've successfully authenticated, but GitHub does not provide shell access.
    Welcome to GitLab, @username!
    ```
{% endif %}

////

///

### Stage 3 — Get the project

Choose the route that matches the repository's current state, then prepare
the local project without losing any existing history.

/// steps

//// step | Get the project

<span id="cloning-the-prodockit-template"></span>

This section explains how to get a project onto the computer.
A **repository** is the project and its saved history. {% if is_surrey %}Surrey GitLab{% else %}GitLab or GitHub{% endif %} keeps
the online copy; a **clone** is the working copy on your computer. Git calls
the online repository connected to a clone `origin`.

There are two different starting points. \ref{tab-manual-project-path} shows
which path to follow; complete only that path.

| Starting point | Path to follow |
| --- | --- |
| Your repository does not exist yet, or exists but is completely empty | [Path 1: start from the template](#manual-install-path-1) |
| Your repository already contains one or more commits | [Path 2: clone the existing repository](#manual-install-path-2) |
/// table-caption | <
    attrs: {id: tab-manual-project-path}

Choose the safe manual project path
///

!!! warning "Do not replace the history of an existing repository"
    Path 1 starts a new history. Never use its history step on a repository
    that already contains work. Use Path 2 so every existing commit, branch,
    and file is preserved.

////

//// step | Return to the repositories directory

Use the lowercase repositories directory and setup environment prepared in
section 3.1. The examples use `repos`; substitute the name you chose.

=== ":material-apple: macOS"

    ``` bash
    cd ~/repos
    source .venv/bin/activate
    ```

=== ":fontawesome-brands-windows: Windows"

    ``` powershell
    cd ~/repos
    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1
    ```

=== ":material-linux: Linux (Ubuntu)"

    ``` bash
    cd ~/repos
    source .venv/bin/activate
    ```

If `cd` reports that the directory does not exist, stop and correct the path
before running any more commands.

The `cd` command changes the current directory. The clone
command creates the project folder inside it. Reactivate this setup
environment in every new terminal until the project build environment is
created.

////

//// step | Path 1: start from the template

<span id="manual-install-path-1"></span>

Create a project from the template with this path when there is no repository for the project yet, or when you
have deliberately created an empty one. It copies the template files, starts
a clean history for your work, and connects that history to your own {% if is_surrey %}Surrey GitLab{% else %}GitLab
or GitHub{% endif %} repository.

1. Create a **blank** repository on the service where the work will be kept.

{% if is_surrey %}
    === ":fontawesome-brands-gitlab: Surrey GitLab"

        On [Surrey GitLab](https://gitlab.surrey.ac.uk){target="_blank" rel="noopener"}, select
        **Surrey Login**, then **New project > Create blank project**.
        Give it the required name, set its visibility to **Private**, and
        untick **Initialize repository with a README**.

{% else %}
    === ":fontawesome-brands-gitlab: GitLab"

        On the GitLab website, select **New project > Create blank project**.
        Give it the required name, set its visibility to **Private**, and
        untick **Initialize repository with a README**.

    === ":fontawesome-brands-github: GitHub"

        On the GitHub website, select **New repository**. Give it the required
        name, set it to **Private**, and leave every **Initialize this
        repository with** option unticked.
{% endif %}

    The repository must be empty because the template provides the README,
    licence, `.gitignore`, and first commit. Initialising any of those on the
    website creates a competing history before your files arrive.

1. Copy the repository's **SSH clone URL** from its web page and keep it for
    the `git remote add` command below. An SSH URL starts with `git@`.

1. Clone the template into a folder named after your project. Replace
    `report-az1234` with the exact repository name you chose.

{% if is_surrey %}
    ``` bash
    git clone git@gitlab.surrey.ac.uk:mb0105/prodockit-template.git report-az1234
    ```
{% else %}
    ``` bash
    git clone git@github.com:buckwem/prodockit-template.git report-az1234
    ```
{% endif %}

    `git clone` downloads both the files and the template's Git history. The
    second name tells Git what to call the new local folder.

1. Change into the project directory as a separate step:

    ``` bash
    cd report-az1234
    ```

1. Check which online repository the clone currently uses:

    ``` bash
    git remote -v
    ```

    Both lines should point to `prodockit-template`. Do not push while that
    is true: `origin` still means the template, not your repository.

1. Move the template's history to a recoverable backup, then start a new
    history. The files in the project are not moved or deleted.

    === ":material-apple: macOS"

        ``` bash
        mv .git ../.report-az1234.git.pdk-template-backup
        git init -b main
        git config core.fileMode false
        ```

    === ":fontawesome-brands-windows: Windows"

        ``` powershell
        Move-Item -LiteralPath .git -Destination ..\.report-az1234.git.pdk-template-backup
        git init -b main
        git config core.fileMode false
        ```

    === ":material-linux: Linux (Ubuntu)"

        ``` bash
        mv .git ../.report-az1234.git.pdk-template-backup
        git init -b main
        git config core.fileMode false
        ```

    !!! info "Why move `.git` instead of deleting it?"
        The hidden `.git` directory contains the template's history and its
        connection to the template repository. Moving it removes both from
        the active project, but the sibling backup remains available if you
        made a mistake. `git init` then creates a clean history owned by this
        project. `core.fileMode false` prevents file-permission changes made
        by Windows or cloud-sync software appearing as edits.

1. Connect the clean local history to your blank online repository. Use the
    SSH URL you copied earlier:

{% if is_surrey %}
    === ":fontawesome-brands-gitlab: Surrey GitLab"

        ``` bash
        git remote add origin git@gitlab.surrey.ac.uk:comm058-2026/report-az1234.git
        ```
{% else %}
    === ":fontawesome-brands-gitlab: GitLab.com"

        ``` bash
        git remote add origin git@gitlab.com:your-namespace/report-az1234.git
        ```

    === ":fontawesome-brands-github: GitHub"

        ``` bash
        git remote add origin git@github.com:your-username/report-az1234.git
        ```
{% endif %}

1. Run `git remote -v` again. Both lines must now show your repository, not
    `prodockit-template`:

    ``` bash
    git remote -v
    ```

    Do not commit or push yet. After the shared installation steps,
    `prodockit sync-repo` will replace the template's own links before your
    first commit is created.

////

//// step | Path 2: clone the existing repository

<span id="manual-install-path-2"></span>

Clone an existing repository with this path when the {% if is_surrey %}Surrey GitLab{% else %}GitLab or GitHub{% endif %} repository already contains work. A
repository with a visible file list or any entry under **Commits** is not
empty. This path keeps its complete history and keeps `origin` pointing to
the same place.

1. Open the repository in {% if is_surrey %}[Surrey GitLab](https://gitlab.surrey.ac.uk){target="_blank" rel="noopener"}{% else %}GitLab or GitHub{% endif %}. Select **Code**, choose **SSH**,
    and copy the URL. Check the browser address and repository name carefully;
    similar project names can lead to cloning the wrong work without an error.

1. Clone that URL. For example:

{% if is_surrey %}
    === ":fontawesome-brands-gitlab: Surrey GitLab"

        ``` bash
        git clone git@gitlab.surrey.ac.uk:comm058-2026/report-az1234.git
        ```
{% else %}
    === ":fontawesome-brands-gitlab: GitLab.com"

        ``` bash
        git clone git@gitlab.com:your-namespace/report-az1234.git
        ```

    === ":fontawesome-brands-github: GitHub"

        ``` bash
        git clone git@github.com:your-username/report-az1234.git
        ```
{% endif %}

1. Change into the cloned project as a separate step:

    ``` bash
    cd report-az1234
    ```

1. Keep its history and configure this clone to ignore file-permission noise:

    ``` bash
    git config core.fileMode false
    ```

1. Confirm the clone is connected to the expected repository and has a
    commit:

    ``` bash
    git remote -v
    git log -1 --oneline
    git status --short
    ```

    `origin` should show the repository you copied. `git log` should show the
    latest saved change. `git status --short` should print nothing, meaning
    the new clone has no unsaved local changes.

1. Create a branch for any configuration changes, using a new branch name:

    ``` bash
    git switch -c setup-prodockit
    ```

    Review and commit on this branch using the project's normal process.

You now have the project locally. The remaining sections are shared by both
paths and install everything needed to edit, build, and publish it.

////

//// step | Confirm the commit identity for this project

Git records an author's name and email address with every commit. Set them
inside this repository so they do not depend on settings from another project:

``` bash
git config --local user.name "Your Name"
git config --local user.email "your.email@example.com"
```

Check what Git will use:

``` bash
git config --local user.name
git config --local user.email
```

Use the email address associated with the {% if is_surrey %}Surrey GitLab{% else %}GitLab or GitHub{% endif %} account that owns
the repository.

////

///

### Stage 4 — Create the project environment

Replace the temporary setup environment with the project's own environment,
then install and verify the Python-based build tools.

/// steps

//// step | Create the project environment and install Zensical

<span id="install-python-and-zensical"></span>

Use the instructions below to create and activate a project-specific Python
\index{Python!virtual environment}, then install Zensical and the PDF system libraries on macOS, Windows, and
Ubuntu. Refer to the [official Python installation
documentation](https://docs.python.org/3/using/) if you use another operating
system.

!!! tip "Automated machine setup"
    For automated machine and project setup, use
    [Build a template site](devcons/bootstrap.md). Its `prodockit bootstrap` command works in
    recoverable stages and checks completed work when it resumes. This page
    remains useful when you need to understand or perform each command
    yourself.

!!! important "Use the project `.venv`"
    Run every Python and prodockit command from this point with the project's
    `.venv` active. If you deliberately use Conda, Poetry, uv, or another
    environment manager, adapt the creation and activation commands and make
    sure `python -m pip` installs into that environment rather than the system
    Python.

The prompt may currently show the parent repositories directory's `.venv`. If it does, run
`deactivate` now. The commands below create a new `.venv` in the current
project directory. This second environment contains the project's build
packages and is the environment used for all later editing and building.

If the project already has a working Python 3.14 environment, reuse it and
skip the environment-creation commands below. These instructions use the name
`.venv`; substitute your environment's name if different. For an older or
damaged environment, follow [Wrong Python version](troubleshooting-installs.md#wrong-python)
before continuing.

!!! warning "Use supported software versions"
    Follow the project's [version requirements](commands/pins.md), rather than
    installing every tool's newest release. Supported versions may be newer
    or older than those already installed: upstream changes have previously
    broken builds. Keep these changes inside the project environment where possible.

1. Follow the instructions below to create and activate the project environment
    with the Python 3.14 interpreter installed at the start of this page.

    === ":material-apple: macOS"

        1. Install \index{Pango}, which is not a Python package, so `pip` cannot install it for you:

            ``` bash
            brew install pango
            ```

        `pdk pdf` downloads verified Pandoc and font archives into this
        project's `.prodockit/cache/pdf/` on first use. To prepare them now:

        ``` bash
        pdk pdf --prepare pandoc --prepare fonts
        ```

        2. Open **Terminal** in your project folder and create the virtual
           environment:

            ``` bash
            "$(brew --prefix python@3.14)/bin/python3.14" -m venv .venv
            ```

            Then activate it as a separate step:

            ``` bash
            source .venv/bin/activate
            ```

            Your prompt gains a `(.venv)` prefix, which is how you know the
            virtual environment is active:

            ``` text
            (.venv) yourname@Mac your-project %
            ```

            It disappears when you close the terminal, and every new one
            needs activating again - or let VS Code do it, which the
            [Python extension](#install-zensical-studio-and-other-plugins)
            below handles for you.

            !!! note "Why the full path to Python"
                macOS may provide another Python. Asking Homebrew for the
                `python@3.14` prefix ensures `.venv` uses the interpreter you
                checked at the start of this page on both Apple silicon and
                Intel Macs.

    === ":fontawesome-brands-windows: Windows"

        1. Prepare the project-local PDF runtimes. Windows x64 uses verified,
           digest-pinned Pandoc, font, and WeasyPrint release archives, so
           do not install MSYS2/Pango or change PATH, the registry, or
           `WEASYPRINT_DLL_DIRECTORIES`:

            ``` powershell
            pdk pdf --prepare pandoc --prepare fonts --prepare weasyprint
            ```

            This command verifies the download, safely extracts it beneath
            `.prodockit/cache/pdf/`, renders a smoke-test PDF, and atomically
            activates it. The first ordinary `pdk pdf` prepares all three
            automatically; bibliography-only use prepares Pandoc alone.
            Windows ARM64 is not a supported PDF target.

        2. The PowerShell execution policy was set when the setup environment
           was created. If you chose not to change it, use **classic CMD** and
           run `.\.venv\Scripts\activate.bat` when activating the project
           environment.

        5. Confirm you are still in your project folder:

            ``` powershell
            cd C:\path\to\your-project
            ```

            !!! warning "Check where you are first"
                The steps above will have moved you. The SSH agent needed an
                Administrator window, which opens in `C:\WINDOWS\system32`, and
                every "close and reopen PowerShell" leaves you in your home
                directory, `C:\Users\yourname`.

                `py -3.14 -m venv .venv` does not object to either. It creates a
                perfectly good virtual environment in the wrong place, and the
                mistake only shows up a step later when `pip install -r
                requirements.txt` cannot find a file that is sitting in your
                project folder all along.

                `pwd` prints where you are.

            Create the virtual environment:

            ``` powershell
            py -3.14 -m venv .venv
            ```

            Then activate it as a separate step. Use the command matching
            your terminal:

            === "PowerShell"

                ``` powershell
                Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
                .\.venv\Scripts\Activate.ps1
                ```

            === "Classic CMD"

                ``` batch
                .\.venv\Scripts\activate.bat
                ```

            Your prompt gains a `(.venv)` prefix, which is how you know the
            virtual environment is active:

            ``` text
            (.venv) PS C:\path\to\your-project>
            ```

            It disappears when you close the terminal, and every new one
            needs activating again - or let VS Code do it, which the
            [Python extension](#install-zensical-studio-and-other-plugins)
            below handles for you.

    === ":material-linux: Linux (Ubuntu)"

        1. Open a terminal and install the graphics libraries
           \index{WeasyPrint} needs:

            ``` bash
            sudo apt update
            sudo apt install -y \
              libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
            ```

            !!! info "Why the three library packages"
                Pandoc hands the result to WeasyPrint, which draws text through \index{Pango} and won't start without it. `libharfbuzz-subset0` is easy to miss - on Debian it's a *separate* package from `libharfbuzz0b`, and WeasyPrint needs this one specifically (glib and fontconfig aren't listed, since `libpango-1.0-0` already depends on them). Skipping this still looks fine until `prodockit pdf`, which then fails with `pandoc exited with status 43` - see [WeasyPrint cannot load its graphics libraries](troubleshooting-installs.md#installtooling-weasyprint-libraries) if that happens.

            !!! warning "Use a supported Debian or Ubuntu release"
                `libharfbuzz-subset0` does not exist on older releases. If the
                package cannot be found, upgrade the distribution rather than
                hunting for a substitute package.

            Pandoc and the PDF fonts are downloaded, verified, and cached by
            `pdk pdf` on first use. To prepare them before building, run:

            ``` bash
            pdk pdf --prepare pandoc --prepare fonts
            ```

        2. Navigate to your project folder, then create a virtual
           environment:

            ``` bash
            python3.14 -m venv .venv
            ```

            Activate it as a separate step:

            ``` bash
            source .venv/bin/activate
            ```

            Your prompt gains a `(.venv)` prefix, which is how you know the
            virtual environment is active:

            ``` text
            (.venv) yourname@host:~/your-project$
            ```

            It disappears when you close the terminal, and every new one
            needs activating again - or let VS Code do it, which the
            [Python extension](#install-zensical-studio-and-other-plugins)
            below handles for you.

////

//// step | Install the project packages and prepare PDF runtimes

<span id="which-pandoc-version"></span>

1. Install Zensical and prodockit inside the active virtual environment. The
    `requirements.txt` file lists the required packages, so install them with
    the environment's own Python:

    ``` bash
    python -m pip install -r requirements.txt
    ```

    Using `python -m pip` ties the install to the active environment. Do not
    use `sudo pip`, and do not continue if the prompt has lost its `(.venv)`
    prefix.

1. Check that the `prodockit` command actually resolves to the one you just installed:

    ``` bash
    prodockit --version
    ```

    `pip` exiting without an error only means the package landed in `.venv` - it doesn't prove your shell finds it there first. An older, separately-installed `prodockit` earlier on your `PATH` shadows it silently, and every command in this guide from here on would run against that instead.

1. Verify the PDF engine before the first real build.

    === ":fontawesome-brands-windows: Windows"

        ``` powershell
        pdk pdf --prepare pandoc --prepare fonts --prepare weasyprint
        ```

        A prepared or already-prepared result proves the project-local
        standalone runtime can render a smoke-test PDF.

    === ":material-apple: macOS"

        ``` bash
        pdk pdf --prepare pandoc --prepare fonts
        python -c "import weasyprint; print(weasyprint.__version__)"
        ```

    === ":material-linux: Linux (Ubuntu)"

        ``` bash
        pdk pdf --prepare pandoc --prepare fonts
        python -c "import weasyprint; print(weasyprint.__version__)"
        ```

    On macOS or Ubuntu, a `cannot load library` error means the native
    libraries from the operating-system step are missing or cannot be found.

1. Check the citation style configured for the project. If it uses
    `harvard-cite-them-right.csl` and that file is missing, download it from
    the project root using the command below. Skip the download if the file
    already exists; do not replace a project's customised citation style.

    === ":material-apple: macOS"

        ``` bash
        curl -fsSL -o harvard-cite-them-right.csl "https://www.zotero.org/styles/harvard-cite-them-right"
        ```

    === ":fontawesome-brands-windows: Windows"

        ``` powershell
        Invoke-WebRequest -Uri "https://www.zotero.org/styles/harvard-cite-them-right" -OutFile harvard-cite-them-right.csl
        ```

    === ":material-linux: Linux (Ubuntu)"

        ``` bash
        curl -fsSL -o harvard-cite-them-right.csl "https://www.zotero.org/styles/harvard-cite-them-right"
        ```


    See [BibTeX bibliography](extensions/bibliography.md) for what this feature
    does and how to configure a different CSL style.

1. Check the repository's own links against `origin`:

    ``` bash
    prodockit sync-repo --check
    ```

    Path 1 still contains the template's repository name, so the check will
    report the changes it needs. Apply them:

    ``` bash
    prodockit sync-repo
    ```

    It reports what it changed, for example:

{% if is_surrey %}
    ``` text
    Detected GitLab remote (https://gitlab.surrey.ac.uk/az1234/report-az1234); updated: repo_url, repo_name, theme.icon.repo, README badges
    ```
{% else %}
    ``` text
    Detected GitHub remote (https://github.com/your-username/report-az1234); updated: repo_url, repo_name, theme.icon.repo, README badges
    ```
{% endif %}

    This rewrites `repo_url`, `repo_name`, `theme.icon.repo` and `edit_uri` in `zensical.toml`, plus the badge row in your `README.md`, to match the `origin` you just set - so your built site and PDF link to your own repository rather than the template's. {% if not is_surrey %}Note `theme.icon.repo` in that list: moving from a GitHub template to a GitLab project switches the header's brand icon to match, which is easy to miss by hand. {% endif %}Only the values that actually needed changing are listed, so the set you see may be smaller.

    On Path 2, the check should normally report that everything already
    matches. If it reports changes, first confirm `git remote -v` shows the
    correct repository. Then run `prodockit sync-repo` to apply them.

    !!! tip "Check it any time"
        `prodockit sync-repo --check` writes nothing and exits non-zero if these have drifted
        from your remote - useful after any later change of host. See
        [Test the built output](devcons/testing.md).

////

///

### Stage 5 — Add editor and rendering tools

Configure the editor and install the optional diagram and mathematics
renderers used by the project.

/// steps

//// step | Install Zensical Studio and the editor plugins **Optional**{: .bg-green}

<span id="install-zensical-studio-and-other-plugins"></span>

Skip this step if you do not use VS Code. When editing an existing
`.vscode/settings.json`, merge the setting below into it rather than replacing
the file and losing the project's other settings.

Now we'll install the \index{VS Code!Zensical Studio} plugin for Visual Studio Code, which provides a set of tools to help you work with Zensical projects, including commands to build and preview your site. Then we'll install a couple of other useful plugins for working with Markdown and TOML files.

1. Start by opening Visual Studio Code and navigating to the Extensions view by clicking on the Extensions icon in the Activity Bar on the side of the window or pressing `Ctrl+Shift+X`/`Cmd+Shift+X`.
1. Install the **Python** extension (published by Microsoft) by searching for "Python" in the Extensions view and clicking **Install**{: .bg-blue}. As well as Python support, this is what makes VS Code notice the `.venv` folder in your project and activate the virtual environment automatically in every new Terminal in VS Code - so you don't have to run `source .venv/bin/activate` by hand each time you open one.

    !!! Tip
        Check it worked by opening a new terminal (**Terminal > New Terminal**) - the prompt should start with `(.venv)`. If it doesn't, reopen VS Code in the project folder, then choose **Python: Select Interpreter** from the Command Palette (`Ctrl+Shift+P`/`Cmd+Shift+P`) and pick the one inside `.venv`.

1. Install the **Zensical Studio** extension by searching for "Zensical Studio" in the Extensions view and clicking **Install**{: .bg-blue} and then **Trust Publisher and Install**{: .bg-blue} when prompted. This extension provides a set of tools to help you work with Zensical projects, including commands to build and preview your site.
1. Follow the instructions on the Zensical Studio extension page to configure
    it. The current template already contains the required setting. If an
    older repository does not, add this to `.vscode/settings.json`:

    ```json
    {
      "files.associations": {
        "*.md": "python-markdown"
      }
    }
    ```

1. Install the **Even Better TOML** extension for Visual Studio Code by searching for "Even Better TOML" in the Extensions view and clicking **Install**{: .bg-blue} and then **Trust Publisher and Install**{: .bg-blue} when prompted. This extension provides syntax highlighting and other features for working with TOML files, which are used for configuration in Zensical projects.
1. Install the **LTeX+ – LanguageTool grammar/spell checking** plugin for Visual Studio Code by searching for "LTeX+" in the Extensions view and clicking **Install**{: .bg-blue} and then **Trust Publisher and Install**{: .bg-blue} to enable spelling and grammar checking for Markdown. Configure the plugin's *language* setting to whichever English (or other language LTeX+ supports) you're actually writing in{% if is_surrey %} - `en-GB` for British English, which is what Surrey coursework expects{% endif %}.

    !!! warning "Get this right, or corrections are confidently wrong"
        Set to the wrong variety, LTeX+ still checks every sentence - it just checks it against the wrong rules, and offers "corrections" for perfectly correct spelling and phrasing in the variety you're actually using. That's worse than no checking at all, since a wrong suggestion looks exactly as confident as a right one.

There are many other extensions available for Visual Studio Code that can help you with your documentation. You can explore the [Visual Studio Code Marketplace](https://marketplace.visualstudio.com/vscode){target="_blank"} to find more extensions that suit your needs.

////

//// step | Prepare optional PDF renderers

Install nothing here for a website-only project. Website mathematics is owned
by Zensical; configure it using the
[Zensical MathJax instructions](https://zensical.org/docs/authoring/math/#mathjax){target="_blank"}.

For PDFs, ProDockit downloads only the renderers that the completed document
actually uses and keeps them in the project's `.prodockit/cache/pdf/` directory.
Mermaid is a Python-only runtime and needs no Node.js, npm, browser or MSYS2.

MathJax 4 is also downloaded and cached automatically, but its small SVG
adapter currently requires Node.js on `PATH`. It does not use npm or a
`node_modules` directory. Install Node.js only when the PDF contains maths:

<span id="install-nodejs"></span>

=== ":material-apple: macOS"

    ``` bash
    brew install node
    ```

=== ":fontawesome-brands-windows: Windows"

    ``` powershell
    winget install OpenJS.NodeJS.LTS
    ```

    Close and reopen PowerShell, return to the project, and reactivate its
    virtual environment.

=== ":material-linux: Linux (Ubuntu)"

    ``` bash
    sudo apt update
    sudo apt install -y nodejs
    ```

Check Node.js when maths is used:

``` bash
node --version
```

An ordinary `pdk pdf` prepares Mermaid or MathJax transparently on first use.
To download and validate them ahead of time without building a site or PDF:

``` bash
pdk pdf --prepare mermaid --prepare mathjax
```

Repeating the command against a healthy cache is a fast, network-free check.
Do not run `npm ci`, `pdk init-tools` or `pdk init-mathjax` for this PDF path.

!!! warning "Check the PDF as well as the website"
    A successful website build does not prove that PDF rendering is ready.
    Run `pdk diag`, then open the generated PDF and inspect a real diagram and
    equation if the project uses them.

////

///
### Stage 6 — Verify and finish

Check the local website and any PDFs you need, then complete only the path
selected in Stage 3. A local build does not publish the website.

/// steps

//// step | Build and finish the setup

Use diagnostics to check for common installation and configuration problems:

``` bash
pdk diag
```

Resolve failures before building the website:

``` bash
zensical build --clean --strict
```

Preview the website locally and open the address printed in the terminal:

``` bash
zensical serve
```

Check the content, navigation and custom styles. Press `Ctrl+C` to stop the
preview before continuing.

If you need a PDF, generate and open it to check its layout, diagrams,
mathematics and references:

``` bash
pdk pdf
```

See [PDF generation](pdf.md) for downloadable PDFs and source bundles. A
successful command cannot detect every visual problem.

////

//// step | Finish Path 1: make and push the first commit

Path 1 has a new local history and an empty online repository. Check exactly
what the first commit will contain:

``` bash
git status --short --untracked-files=all
```

Generated dependencies such as `.venv`, `node_modules`, and the installed
MathJax bundle should not appear because `.gitignore` excludes them. Stop if
generated files or private material appear, and correct the ignore rules
before selecting files.

Select the project's content, configuration and build instructions, then
review what will be saved:

``` bash
git add -A
git diff --cached
```

Press `q` to leave the review. Save the first version locally:

``` bash
git commit -m "Initial commit"
```

Follow [Publish the website](getting-started.md#stage-6-save-and-publish-optional)
to enable Pages for your chosen host and check the build automation. Your
repository and `origin` were already set up in Stage 3; do not create them again.
When ready, send the commit to that repository:

``` bash
git push -u origin main
```

`git commit` saves the first version locally. `git push` copies that commit to
{% if is_surrey %}Surrey GitLab{% else %}GitLab or GitHub{% endif %} and `-u origin main` records where later pushes should go.
Wait for its build to succeed, then open the Pages link on the repository's
front page as described in the publishing instructions.

////

//// step | Finish Path 2: review and publish the changes

Installing dependencies may leave source files unchanged, but configuration
and repository-link updates can change them. Review the results on your setup
branch before committing:

``` bash
git status --short --untracked-files=all
```

This lists changed and new files. Check edits to tracked files separately:

``` bash
git diff
```

Press `q` to leave the review. Confirm that content and custom settings are
preserved, and that dependency, stylesheet, script and editor changes are
intentional. Review new files separately; `git diff` does not show their content.

Follow the existing project's branch, commit, review and publishing process.
Keep its remote and build automation; do not create a new initial history or
force-push. If there are no project changes, no commit is needed. See
[Review the project changes](getting-started.md#stage-7-review-the-project-changes)
for the types of configuration to check; its Adopt-specific file replacement
rules apply only if you also run Adopt.

////

///

## Understand the completed project {: #manual-completed-project }

This section explains how ownership and future maintenance depend on the manual
path used to obtain the project.

### Know what becomes yours {: #manual-project-ownership }

A manual installation gives you direct responsibility for the commands and
project decisions in this section. Use the [project structure
overview](installation.md#installation-project-structure) to distinguish
source files from the local environments, installed renderer bundles, caches,
and generated output that can be recreated.

The maintenance model depends on the path used to obtain the project. Path 1
starts from `prodockit-template`, so its template manifest continues to
classify template-managed, project-owned, and generated files. Path 2 keeps
whatever ownership and maintenance metadata the existing repository already
had; manually installing Prodockit does not create a template relationship.

Your authored content and project-specific overrides remain yours in both
paths. Running the commands manually does not transfer ownership of those
files to Prodockit.

### Keep the project current {: #manual-project-maintenance }

Start every maintenance pass in the active project environment, with existing
work saved on a branch. Follow the project's supported version requirements
and the platform-specific installation steps above; do not update every
dependency independently to its newest version. Run Diagnostics before
rebuilding, and generate a PDF only if your project needs one:

```bash
pdk diag
zensical build --clean --strict
pdk pdf
```

For a Path 1 template project, preview `pdk template-sync` and follow the
Template Sync review workflow when an update is available. For a Path 2
project without template metadata, maintain its files through its existing
workflow. If you later want Adopt to align the toolchain and selected
components, begin with `pdk adopt --dry-run` and review the proposed scope
before applying it.

## Where to go next {: #installtooling-where-to-go-next }

Choose the route that matches the result:

- If setup has not completed or any check fails, use
  [Troubleshooting](troubleshooting-installs.md).
- If setup has completed and `pdk diag` passes, continue with
  [Publish a document](publishing.md).
