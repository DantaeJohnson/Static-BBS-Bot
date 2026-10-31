# Static BBS Bot

**Plays the Story mode of Bleach: Brave Souls for you.**

Static BBS Bot plays Bleach: Brave Souls inside **BlueStacks** (a free program that runs
Android games on your PC). It looks at the game screen, works out what's happening, and
taps the right buttons. It picks the next story stage, starts the quest, battles on AUTO,
skips cutscenes, collects rewards and moves on to the next quest, over and over. It stops
on its own when the story is finished.

While it plays, **your PC is free to use**. The bot never moves your mouse or types on your
keyboard. It sends taps straight into BlueStacks, which can sit in the background or be
minimised.

> ⚠️ **Please read:** This is an unofficial, fan-made tool. It isn't made or approved by KLab
> (the game's makers). Using automation tools may go against the game's Terms of Service.
> **You use it at your own risk.**
>
> 💎 **Your Spirit Orbs are safe by default.** The bot never spends Spirit Orbs unless you turn
> that on yourself, and even then it never goes over a limit you choose.

---

## Contents

1. [What you need](#1-what-you-need)
2. [Download the bot](#2-download-the-bot)
3. [Install Python](#3-install-python)
4. [Set up BlueStacks](#4-set-up-bluestacks)
5. [Open the bot for the first time](#5-open-the-bot-for-the-first-time)
6. [Connect the bot to BlueStacks](#6-connect-the-bot-to-bluestacks)
7. [Start playing](#7-start-playing)
8. [Pausing and stopping](#8-pausing-and-stopping)
9. [Settings explained](#9-settings-explained)
10. [Why did the bot stop?](#10-why-did-the-bot-stop)
11. [Troubleshooting](#11-troubleshooting)
12. [Updating the bot](#12-updating-the-bot)
13. [Extra: playing on the Steam (PC) version instead](#13-extra-playing-on-the-steam-pc-version-instead)

---

## 1. What you need

Go through this list before you start. Everything on it is **free**.

| ✔ | Requirement | Details |
|---|---|---|
| ☐ | **A Windows PC** | Windows 10 or Windows 11, 64-bit. Mac and Linux are not supported. |
| ☐ | **BlueStacks 5** | The free Android emulator. Download it from [bluestacks.com](https://www.bluestacks.com). |
| ☐ | **Bleach: Brave Souls installed inside BlueStacks** | Install it from the Google Play Store *inside* BlueStacks and log in to your account. |
| ☐ | **Story mode unlocked** | You need to be able to open the **Story** map in the game. |
| ☐ | **Python 3.12** | The free programming language the bot is written in. Step 3 shows how to install it. |
| ☐ | **An internet connection** | Needed the first time you open the bot, to download what it needs (about 300 MB). |
| ☐ | **About 1 GB of free disk space** | For the bot and its downloaded parts. |
| ☐ | **A strong enough team** | The bot plays on AUTO. If your team can't beat a stage on AUTO, the bot can't either. |

---

## 2. Download the bot

1. On this page, click the green **`<> Code`** button near the top, then **Download ZIP**.
2. Open your **Downloads** folder, right-click the ZIP file and choose **Extract All…**, then **Extract**.
3. Move the extracted folder somewhere easy to find, for example your **Documents** folder.
   You can rename it to `Static BBS Bot`.

> ❗ **Don't run the bot from inside the ZIP file.** Always extract it first. If you double-click
> files inside the ZIP without extracting, the bot won't work.

Inside the folder you should see files such as `Start Static BBS Bot.bat`, `main.py`,
`README.md`, and folders named `assets`, `bbsbot` and `gui`.

---

## 3. Install Python

The bot needs Python to run. You only do this once.

1. Go to **[python.org/downloads/windows](https://www.python.org/downloads/windows/)**.
2. Under **Python 3.12**, download the **Windows installer (64-bit)**.
   *(3.11 and 3.13 also work. Avoid brand-new versions like 3.14, because some parts the
   bot needs may not support them yet.)*
3. Run the installer. **On the very first screen, tick the box that says
   ✅ "Add python.exe to PATH"** at the bottom. This is the most important step.
4. Click **Install Now** and wait for it to finish, then click **Close**.

> Already have Python? That's fine. The bot finds it automatically.

---

## 4. Set up BlueStacks

You only do this once. Open **BlueStacks 5**, then open its **Settings**: click the ☰ menu at
the top right, or the ⚙️ gear icon on the right-hand side bar.

### 4a. Set the screen size

1. In Settings, open the **Display** tab.
2. Set **Display resolution** to **1600 × 900** and the orientation to **Landscape**.
3. Click **Save changes**. BlueStacks may ask to restart, which is fine.

*(Other widescreen sizes such as 1920 × 1080 also work, but 1600 × 900 is the most reliable.)*

### 4b. Turn on Android Debug Bridge (ADB)

ADB is how the bot sends taps into BlueStacks without using your mouse.

1. In Settings, open the **Advanced** tab.
2. Turn **ON** the switch called **Android Debug Bridge (ADB)**.
3. Under the switch you'll see an address like **`127.0.0.1:5555`**. Write it down, because
   you'll need it in step 6.
4. Click **Save changes**.

---

## 5. Open the bot for the first time

1. Open the bot's folder and **double-click `Start Static BBS Bot.bat`**.
2. **If Windows shows a blue box saying "Windows protected your PC":** click **More info**,
   then **Run anyway**. Windows shows this for any program it doesn't recognise. The file
   only sets up and opens the bot.
3. A black window opens and sets everything up. **The first time, this takes a few minutes**
   because it downloads about 300 MB. Leave it alone until it says *Setup complete*.
4. The bot's window opens: a dark window with **STATIC BBS BOT** at the top left.

From now on, double-clicking `Start Static BBS Bot.bat` opens the bot straight away, with no
more setup.

> 💡 You can make a shortcut: right-click `Start Static BBS Bot.bat` → **Show more options** →
> **Send to** → **Desktop (create shortcut)**.

---

## 6. Connect the bot to BlueStacks

1. Make sure **BlueStacks is open**.
2. In the bot, click **⚙ Settings** on the left side.
3. In the **Connection** box at the top:
   * **Play on:** choose **BlueStacks (ADB) – PC stays usable**.
   * **ADB address:** type the address from step 4b (usually `127.0.0.1:5555`).
     You can also leave it empty and the bot will try to find BlueStacks itself.
4. Click the orange **Test connection** button.
   * If the bot asks **"Download ADB?"**, click **Yes**. It downloads a small official tool
     from Google (about 10 MB). This only happens once.
   * ✅ Success looks like: **"Connected to BlueStacks - screen 1600×900."**
   * ❌ If it says it couldn't reach BlueStacks, see [Troubleshooting](#11-troubleshooting).

The **GAME** box at the bottom left of the bot also shows the connection, with a green dot
when connected.

---

## 7. Start playing

1. In BlueStacks, open **Bleach: Brave Souls** and go to the **Story** map
   (the screen with the numbered stages, **MAIN** / **SIDE** tabs and **Select Part** button).
2. In the bot, click **◆ Dashboard** on the left.
3. **Pick a mode:**

   | Mode | What it does | Where to start in the game |
   |---|---|---|
   | **Story Progress** | Plays every uncleared story stage in order, then stops when the story is finished. | The **Story map** |
   | **Farm Stage** | Replays one stage again and again with **Retry** (for drops or EXP). | That stage's **Prepare for Quest** screen |

4. **Check the Spirit Orb options** in the *Soul Tickets & Spirit Orbs* box. They're
   **off** by default, which means the bot spends **no orbs at all**. See
   [Settings explained](#9-settings-explained).
5. Click the big orange **▶ Start** button.

That's it. Watch the **Live activity** box to see what the bot is doing. The counters show
how many quests it has cleared. You can now use your PC normally; just **don't close BlueStacks**.

---

## 8. Pausing and stopping

| To… | Do this |
|---|---|
| **Pause / resume** | Click **Pause** in the bot, or press **F8** on your keyboard. |
| **Stop** | Click **■ Stop** in the bot, or press **F9** on your keyboard. |

> ⌨️ F8 and F9 work even while you're in another program, so pressing them anywhere pauses
> or stops the bot. You can change these keys in **Settings → Hotkeys & interface**.

**Things that will stop the bot from working:**

* Closing BlueStacks, or the game closing inside it.
* Your PC going to **sleep**. Before a long run, set Windows *Settings → System → Power →
  Sleep* to **Never**. The screen turning off is fine.
* Turning off ADB in BlueStacks.

Minimising BlueStacks or putting other windows on top of it is fine.

---

## 9. Settings explained

All settings save automatically. The most important ones are on the **Dashboard**; the rest
are on the **Settings** page.

### Spirit Orbs (premium currency)

| Setting | Default | What it means |
|---|---|---|
| **Use Spirit Orbs to buy Soul Tickets** | **Off** | When your Soul Tickets run out, buy more with orbs. |
| **Orb spending limit** | 50 | The most orbs the bot may spend on tickets in one run. It never goes over. |
| **Orbs per refill** | 10 | How many orbs one ticket refill costs in your game. |
| **When out of tickets** | Wait for recharge | If it isn't buying tickets: **wait** for them to refill, or **stop**. |
| **Expand a full character box** | **Off** | When your character box is full: **off** = stop the bot, **on** = pay 5 orbs for 5 more slots and keep going. |
| **Orb limit for character slots** | 25 | The most orbs the bot may spend on character slots in one run. |

When any orb option is on, the bot asks you to confirm how many orbs it may spend each time
you press Start. Before any tap that spends orbs, it takes a fresh look at the screen and
double-checks the button.

### Battle and limits

| Setting | Default | What it means |
|---|---|---|
| **Stop after** | No limit | Stop after this many cleared quests. |
| **Use Revive Candles** | Off | Revive your team when it's defeated (at most once per quest, 5 per run). **Off** = give up that try and retry. |
| **Skip story scenes** | On | Presses **Skip** on cutscenes and dialogue. |
| **Keep AUTO battle on** | On | Turns AUTO on if it's off. |
| **Stop after losses in a row** | 2 | Stops if the same quest is lost this many times (your team may need to be stronger). |
| **Stop after time** | No limit | Stop after this many minutes. |

You normally never need to change anything under **Detection & timing**.

---

## 10. Why did the bot stop?

The bot always writes the reason at the bottom of the Dashboard and in **Live activity**.

| Message | What it means | What to do |
|---|---|---|
| **Story complete – there's no more story to play** | You've finished all the story there is. 🎉 | Nothing! Come back when new story is released. |
| **Every stage on this part of the story is cleared** | No uncleared stage could be found on the map. | Open the next part with **Select Part** in the game, then press Start. |
| **The next stage is locked** | The next stage needs something first, such as a level or another story requirement. | Unlock it in the game, then press Start. |
| **Character box is full** | Your character box has no room left. | Sell or ascend some characters, or turn on **Expand a full character box**. |
| **Out of Soul Tickets** | You ran out of tickets and the bot was set to stop. | Wait for tickets to refill, or change **When out of tickets** to *Wait for recharge*. |
| **Lost 2 times in a row** | Your team couldn't beat that quest on AUTO. | Make your team stronger, then press Start. |
| **Reached the clear limit / time limit** | It did what you asked. | Nothing to do. |
| **Lost the game screen for over a minute** | The bot couldn't see BlueStacks. | Check BlueStacks is open, then press Start. |
| **Stuck: no known screen** | The game showed something the bot doesn't recognise. | See *"The bot doesn't recognise a button"* below. |

---

## 11. Troubleshooting

**Double-clicking the `.bat` file says "Python was not found".**
Install Python as shown in [step 3](#3-install-python). Make sure you ticked
**"Add python.exe to PATH"**. If you forgot, run the Python installer again, choose
**Modify**, and tick it. Restart your PC, then try again.

**The first-time setup says "Package install failed".**
Check your internet connection and try again. If you have a very new Python (3.14 or
later), install **Python 3.12** too, delete the bot's `.venv` folder, and try again.

**"Test connection" can't reach BlueStacks.**
* Is BlueStacks open, with the game screen showing?
* Is **Android Debug Bridge** turned **on** in BlueStacks → Settings → Advanced?
* Does the **ADB address** in the bot match the one shown under that switch? Try leaving it
  **empty** so the bot searches for BlueStacks itself.
* Restart BlueStacks, then click **Test connection** again.

**It says the screen isn't 16:9.**
Set BlueStacks to **1600 × 900, Landscape** (step 4a).

**The bot doesn't recognise a button (or says "Stuck").**
Different game versions or languages can draw buttons a little differently. You can teach
the bot:
1. In the game, go to the screen where it got stuck.
2. In the bot, click **▣ Templates** → **Test detection**. Green boxes show what it recognises.
3. Click **Capture from game**, drag a tight box around the button, pick its name from the
   list, and click **Save**.

The bot also saves a picture of every screen it doesn't recognise in `logs/unknown_screens/`,
and a picture of where it stopped in `logs/screenshots/`.

**The bot window doesn't open at all.**
Double-click **`Run with console (debug).bat`** instead. It shows any error message.
Errors are also saved in `logs/crash.log`.

**I want to see exactly what the bot did.**
Click **≡ Logs** in the bot, or open the `logs` folder:
* `run_….log`: everything the bot saw and did
* `runs.csv`: one line per quest (result and time taken; opens in Excel)
* `taps.csv`: every tap the bot made

---

## 12. Updating the bot

1. Download the new ZIP from GitHub, as in step 2, and extract it.
2. Copy these folders from your **old** bot folder into the **new** one, so you keep your
   settings and any buttons you captured:
   * `config`
   * `user_templates`
3. Double-click `Start Static BBS Bot.bat` in the new folder. It runs the first-time setup again.

---

## 13. Extra: playing on the Steam (PC) version instead

The bot can also play the **Steam / PC version** of the game. In this mode it uses your **real
mouse**, so you can't use the PC while it runs.

1. Run the game **windowed** at **1600 × 900**, and don't minimise it.
2. In the bot: **Settings → Connection → Play on: PC game window**.
3. Open the Story map and press **Start**. Don't touch the mouse.
   Moving the mouse into a corner of the screen is an emergency stop.

---

## Credits

* Default button images and the original idea come from
  [bbs-auto-farmer](https://github.com/xJohnnyrl/bbs-auto-farmer) by xJohnnyrl (MIT License).
  See `THIRD_PARTY_NOTICES.txt`.
* Bleach: Brave Souls and its artwork belong to KLab Inc. and Shueisha. This project isn't
  affiliated with them.
