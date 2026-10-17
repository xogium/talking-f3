<!-- SPDX-FileCopyrightText: 2022, 2026 Casey Reeves <contact@xogium.me>
     SPDX-License-Identifier: MIT -->

# Zoom F3 #
This guide is exclusively used for the F3 field recorder from Zoom, and is not applicable to any other models, not even in the same F series.

This documentation is based on firmware version 2.20 of the F3 (it was first written for 2.0). Make sure to run the same version in case the interfaces changes. Should it change in the future, this documentation will be updated to reflect such changes.

# The talking F3 (recommended) #
Since 2026, there is a better way for blind people to use the F3: the **talking F3**. It is a patched version of Zoom's own firmware 2.20 that speaks what is on the screen, through the headphones. It is now the preferred way of using the F3 without sight.

The rest of this guide is left as it was written in 2022. It is still for you if your F3 runs a firmware older than 2.20, or if you would rather not have a talking F3. The physical description, the button layout, the menu list and the input settings remain useful for everyone, talking F3 or not. Notes about the talking F3 have been added where they matter, marked **Talking F3:**.

## What it speaks ##
* The menus as you move through them, and which option is currently selected in check box menus.
* Language names in the Language menu, each in its own language.
* Popups such as VOLUME, Hold, No SD Card and so on, including values that change while the popup is shown.
* Execute/cancel and OK/cancel dialogs, with the option you are on.
* The waveform magnification popup.
* The Set Date/Time screen: which field you are on, its value, and when you start or finish editing it. Setting the date and time no longer needs sighted help or the bluetooth app.
* The Finder: file names, and where you are in the list.
* Playback: the name of the file being played, and the file info pages (date and time, format, length).
* The Versions screen.
* The user defined name editor: every key as you move, each character you type or delete, and the whole name when you reach OK.
* On the home screen, while not recording or playing, pressing stop tells you the remaining recording time, the battery level, and the name the next recording will get (so you can check it before pressing record).
* During playback, after you fast forward or rewind (holding the enter or back button), it tells you how much time is left in the file.

It speaks in the language the F3 is set to: English, French, German, Italian, Spanish, Chinese or Japanese. The voice follows the headphone volume buttons, and it is only heard in the output: it never ends up in your recordings. A short chime tells you when the F3 has started and the voice is ready.

## The patcher ##
You make the talking firmware yourself with the **Talking F3 Patcher**, a single web page that works in any web browser, on Windows, macOS or Linux: <https://xogium.github.io/talking-f3/>. You can also save that page and use it from your own computer. It works offline: nothing is uploaded anywhere. It is accessible with a screen reader.

The patcher asks for Zoom's official F3 firmware, version 2.20: download [F3_v2.20_E.zip](https://zoomcorp.com/documents/2366/F3_v2.20_E.zip) from zoomcorp.com and give the patcher that zip file as it is, no need to unzip it. It then lets you choose:
* which languages to include (languages left out fall back to English),
* the voice variant, its pitch and its speed (up to 1000 words per minute), with a different speed per language if you wish,
* the sound quality: higher quality sounds clearer but takes more room. The F3 has room for about 4 MB of voices, enough for all seven languages at the standard quality; with a single language you can choose the highest quality. The patcher shows an estimate of the size as you change the settings,
* how loud the voice is,
* whether to play the start-up chime.

A "Listen to a sample" button lets you try your settings before building. Building takes about a minute and produces a new F3SYSTEM.BIN.

If your F3 runs a firmware older than 2.20, first update it to 2.20 with Zoom's own file, the same way as described below.

## Installing it ##
* Copy the new F3SYSTEM.BIN to the top level of the micro sd card, not inside a folder. If the card already has an F3SYSTEM.BIN, replace it.
* Use fresh batteries or the power adapter: the update does not run on low battery.
* With the F3 switched off, insert the card, hold the play/pause button and switch the F3 on.
* The F3 offers to update. Choose execute and confirm. Do not switch it off or remove the card while it updates.
* When it is finished, switch the F3 off and on again. After a moment you hear the chime, and the F3 speaks as you use it.

To go back to the normal firmware, do the same steps with Zoom's original F3SYSTEM.BIN version 2.20. The patch never touches the F3's startup code, so going back always works.

The talking F3 is an independent project, not made or supported by Zoom.

## What does not talk (yet) ##
A few screens appear before the F3's audio is switched on, so nothing can be heard on them, not even the chime. You have to handle them by counting button presses, as before.

* **First power-up after a factory reset.** The F3 asks for the language, then for the date and time. Neither screen talks. To get through them:
	* On the language screen, English is selected. Press enter to keep it. If you prefer another language, you can change it later in system, language, which talks.
	* On the date and time screen, press up once to reach the OK option, then enter.
	* In short: enter, up, enter. You can set the correct date and time later from system, date/time, which talks.
* **The bluetooth function screen** that shows up at power-up when the BTA-1 dongle is plugged in (see "Using the optional bluetooth adapter" below). Other accessories may show a similar screen. The first item, off, is always selected; press enter to keep bluetooth off, or move down to the function you want.
* **Factory reset.** After you execute a factory reset, the F3 switches itself off without saying anything. This is normal. The talking F3 warns you about it in the factory reset dialog. When you switch it back on, see the first point above.
* When you skip between files during playback, the file name may be read twice in some cases.

# Caution #
Any menu in this recorder wraps around. Meaning that if for example you press the menu button, then go up once, you move all the way to system instead of remaining on finder. It is hence very important to exactly keep track of how many times you go up or down.

However dialogs that ask you a question of execute/cancel type do not wrap around. The up button moves to execute, the down button moves to cancel. Every time such a dialog is shown, you will be positioned on the cancel option.

After you have done something in a menu, the recorder remembers at what position you were on until you power it off. For example, if you are on the input 1 source and select mic+48v, it will put you on the menu item to select the source if you reopen the input 1 settings.

Since there is a limited number of buttons, what each of them does depends on the currently active screen.

## Buttons and connectors ## 
Hold the recorder so that the row of 4 buttons is closest to you, right below the lcd display.

### Left side, top to bottom ###
* play/pause button
* stop button
* menu button
* USB-C connector
* micro sd slot behind protective cover

### front ###
* 2x XLR input connectors

### right side ###
* record / stop record / hold switch
* bluetooth dongle connector, covered
* power button

### back, left to right ###
* 3.5mm jack line out connector
* 3.5 mm jack headphone connector
* headphone volume buttons, left is lower, right is higher

#### top of the recorder, left to right ###
* back button
* up button
* down button
* enter button

### List of actions performed by the buttons ###
* back button
	* When on the home screen, this button controls the magnification settings for the first input.
	* When the magnification settings for the first input are displayed, this button lowers it.
	* When in a menu of some kind, it goes back to the previous menu.
	* When playing a file it does 3 things:
		* Moves to the previous file.
		* When held, it moves backward in the same file.
		* Moves to the previous mark in a file, should it have any.
* up button
	* On the home screen, this button opens the settings for the first input.
	* In a menu or a dialog, this button moves up.
	* When the magnification settings for the first input are displayed, this button raises it.
* down button
	* On the home screen, this button controls the magnification settings for the second input.
	* In a menu or dialog, it moves down one item.
	* When the magnification settings for the second input are displayed, this button lowers it.
	* When a file is playing or paused, press it once to select the delete option.
* enter button
	* On the home screen, this button opens the settings of the second input.
	* When in a menu or dialog, use it to confirm your selection.
	* When playing a file, it does 3 things:
		* Moves to the next file.
		* When held, it moves forward in the same file.
		* Moves to the next mark in a file, should it have any.
* play/pause button
	* This plays the currently selected file or pauses it, if it is already playing.
	* When in the line out volume management menu, pressing this button once will play back a tone into the line out port so you can adjust the level appropriately. Press it again to stop the tonality.

## Menu list ##
* finder (skipped, not very useful to blind people)
	* **Talking F3:** the finder talks, so it becomes useful: it reads each file name as you move through the list.
* recording
	* rec file name (check box menu)
		* date
		* user defined name (skipped, but doable through the use of the bluetooth app and adapter)
			* **Talking F3:** the name editing screen talks, so you can type a name yourself. See "Typing a user defined name" below.
	* sample rate (check box menu)
		* 44.1khz
		* 48khz
		* 88.2khz
		* 96khz
		* 192khz
	*	 file format (check box menu)
		* mono
		* stereo
	* pre rec (check box menu)
		* off
		* on (6, 3 or 2 seconds depending on sample rate)
	* sound marker (check box menu)
		* off
		* on
	* rec counter
		* elapsed time
		* remaining time
* output
	* hp alert vol
		* -20dbFS , up = increments towards 0, down = decrements, steps of 1
	* line out level
		* -1dbFS , up = increments towards 0, down = decrements, steps of 1
		* down all the way is mute
		* up once from mute is -48db
		* maxes at +24db
		* saves maybe when going back?
	* line out limiter
		* off
		* on
	* line out delay
		* 0ms , up = increments, down = decrements, steps of 1ms
		* clamp to 0
* usb audio (see below)
* file transfer (see below)
* timecode (TCA-1)
	* Note: this list was read from the firmware 2.20 data, not checked on a real F3 with a TCA-1.
	* mode
		* on/off (check box menu)
			* off
			* int free run
			* int rec run
			* time of day
			* ext
			* ext auto rec
		* timecode output (check box menu)
			* always
			* rec only
		* ext continuous (check box menu)
			* on
			* off
	* jam
	* frame rate (check box menu)
		* 23.976 NDF
		* 24 NDF
		* 25 NDF
		* 29.97 NDF
		* 29.97 DF
		* 30 NDF
		* 30 DF
	* user bits
		* mode (check box menu)
			* uu uu uu uu
			* mm dd yy uu
			* dd mm yy uu
			* yy mm dd uu
		* edit
	* auto rec delay
	* connect to (check box menu)
		* ZOOM F6
		* other
	* firmware (TCA-1)
* system
	* language (check box menu
		* english
		* francais
		* deutsch
		* italiano
		* espanol
		* chinese
		* japanese
		* **Talking F3:** each language name is spoken in its own language, and the voice switches language with the F3.
	* date/time (skipped, very difficult to adjust without sighted assistance, only possible way is through the bluetooth adapter)
		* **Talking F3:** set date/time talks: it tells you which field you are on (year, month, day, hour, minute, OK) and its value. Press enter to edit a field, up and down to change it, enter to finish. The date format setting talks too.
	* lcd 
		* backlight (check box menu)
			* off
			* on
			* 1 min
		* contrast
			* ranges from 1 to 10, default is 5. Does not wrap around
	* power
		* battery type (check box menu)
			* alcaline
			* ni-mh
			* lithium
		* auto power off (check box menu)
			* off
			* 10 minutes
			* 60 minutes
			* note: does not apply when the recorder is powered over usb-C.
	* sd card
		* format
		* quick test
		* full test (can be very long, 27 minutes for a 16 GB micro sd)
	* bluetooth function
		* F3 control
		* timecode
		* Note: in firmware 2.20, this menu lists F3 control, Handy Control&Sync, and UltraSync BLUE (with paired device, new device and information).
	* timecode settings
		* information
		* home time display (check box menu)
			* rec & timecode
			* timecode
			* rec time
	* versions
		* displays the firmware version of the F3
		* **Talking F3:** the versions screen is read out.
	* factory reset
		* execute/cancel dialog
		* **Talking F3:** after execute, the F3 switches itself off silently. On the next power-up, the language and date/time screens don't talk: press enter, up, enter (see "What does not talk (yet)" above).

## Input settings ##
The following settings apply to the inputs and can be accessed with their respective buttons from the home screen.
* on/off (enable or disables the input, wraps around)
* source (check box menu)
	* mic
	* mic +24 or 48v, depending on phantom power voltage setting
	* line
	* line +24 or 48v, depending on phantom power voltage setting
* phantom power voltage (check box menu)
	* 24v
	* 48v
* hpf (does not wrap around)
	* from off to 240 hz, increments in steps of 10 hz
* invert phase (check box menu)
	* off
	* on
* delay ( does not wrap around)
	* 0.0 ms default
	* increments of 0.1 ms

## How to connect the recorder in file transfer mode ##
If you wish to access the micro sd card directly from the zoom, connect an usb type C to usb type A cable or usb-C to usb-C cable to your computer, then do the following:
* Press the menu button.
* Go up 2 times until you reach file transfer then validate with the 
confirm button.
* When you are done, press the back button to get back to the menu, then menu to go back to the home screen.

## USB audio interface mode ##
To enable the F3 to act as an audio interface, proceeed as follows:
* Open the menu using the menu button.
* Go down 3 times to select USB IF, and confirm with enter.
* This opens up a dialog box asking you to which device you wish to connect the interface to, pc/mac, or phone/tablet. Pc/mac will rely on usb-C as a power source, while phone/tablet will rely on battery power. Make your selection with up or down button then confirm with enter.
* Once done, you have the choice between 32 bit float or 24 bit linear. Press up or down to move around, and enter to confirm.

After these actions have been performed, you get back to the home screen with the recorder now acting as a sound card for whichever device you connected it to. Pressing the menu button will offer you a few options:
* Exit USB interface: use this to exit this mode. Confirm with enter, move up to select execute, then press enter again.
* Loopback mode: this opens a submenu with on/off.
* Mono mix: this also opens a submenu with on/off.
* Direct monitoring: also opens a submenu with on/off.

## Using the optional bluetooth adapter ##
Zoom sells the BTA-1 dongle which allows you to control the recorder using the F3 Control Android and iOS apps.

This app makes using the unit a little bit easier for blind people, as you can then modify the source for the inputs, modify the sample rate, the file format and so on. It doesn't let you adjust settings like backlight and etc., so for those, you do have to tweak them directly on the recorder.

Here's a list of what you can do using this app:
* Play recordings (through the F3 itself !)
* Move to previous/next file.
* Pause/stop playback.
* Record a new file.
* Add marks into your recording (so-called media cues).
* Disable and enable inputs.
* Configure each input (source, phase, delay, high pass filter).
* Configure magnification of the waveform.
* Access the menu to set various parameters.
	* Finder displays the content of the micro sd, remaining free space, total used space.
	* Recording settings (sample rate, file format, pre-record function ...)
	* Date/time settings (set date and time, set date and time format).
	* Versions (displays the version of the F3 firmware and F3 Control app).

When setting the date and time, it can be a little confusing because when you get asked for confirmation if you wish to do this, you might expect to land on a dialog box with day, month, year, etc. Instead, the bluetooth app somehow sends the current date and time of your phone over bluetooth to the recorder, which sets its date and time settings based on this information.

### How to connect ###
*  Remove the bluetooth dongle cover entirely and gently insert the dongle into the slot until you hear it click into place. No need for force, be very gentle.
* Power up the unit. If you have headphones plugged in, you'll notice that unlike before, it doesn't give you instant monitoring, because of the menu that pops up.
* This menu will show up every time you boot up the unit, as long as the dongle is plugged in, and the selection will not be remembered. meaning you will always be on the first item by default.
	* bluetooth function
		* off
		* F3 Control
		* Timecode
* **Talking F3:** this screen appears before the F3's audio is switched on, so it does not talk. Off is selected: press enter to keep bluetooth off, or count your way down to the function you want, then press enter.

### Android app ###
Note: if at all possible, I would recommend to not use the Android app, instead use the iOS one.

The accessibility of the Android app is so-so, you sometimes get stuck in menus, the way to use the hpf menu is unclear and unintuitive at least when you're blind. You have to be quite precise when tapping on icons even with talkback active, and you have absolutely no feedback on the activation of any icon, by sound or vibration. This makes it relatively difficult to use, given you can't know for sure if you have successfully inserted a mark in a file, for example.

So, it is possible to use it, but I wouldn't rely on it.

### iOS app ###
Unlike the Android app, I've not found one single issue with the iOS one. Every item is easy to tap and doesn't require precision, you get feedback about them, both vibration and sounds if you enabled them, and the hpf menu is easy to set, since it is a potentiometer. I'd rate this app's accessibility as perfect.

## Magnification of the waveform ##
The F3 lets you change the magnification of the waveform before or during a recording. What this means is that you have actually some very minimal control over the input gain in a sense, although it recording in 32 bit float means that the input gain ultimately doesn't matter. But this can imply potentially 3 things:
* It makes the wave form that is displayed on the recorder and on your phone if you use the bluetooth adapter larger or smaller.
* It raises or lowers the volume at the headphone jack.
* If done **before** starting the recording, it will affect the gain used for it. If done during a recording, only the output and the waveform size will be affected.

To adjust magnification, do the following:
* For the first input, press the back button.
	* If you wish to lower it, press the back button again.
	* If you wish to raise it, press the up button.
* The same applies for the second input, but with the down and confirm buttons, respectively.

Note that the magnification screen isn't displayed very long, so you must act quickly to adjust the setting, or it will disappear and you will wonder why it didn't work and risk altering input settings instead.

**Talking F3:** the magnification popup is spoken: the input when it opens, then the new magnification at each press.

## Deleting files ##
If you wish to delete a file, proceed as follows:
* Start the playback of the desired file.
* While it is playing or paused, press the down button to select delete, then enter to confirm.
* Move with the up or down button to select execute and confirm with enter.

## Typing a user defined name ##
This only applies to the talking F3; without it, use the bluetooth app as described above.

Go to recording, rec file name, then user defined name and press enter. The editor opens with three character sets:
* uppercase letters: A to Z, then underscore, dash and space,
* lowercase letters: a to z, then underscore, dash and space,
* numbers and symbols: 1 to 9, 0, then + = ! # ' , ; ( ) [ ] { } $ @ ^ ` ~ and space.

After the characters of the current set come five more keys: character set (switches between the three sets), delete, cursor left, cursor right, and OK. Up and down move between the keys and wrap around. The editor opens on OK.

* The talking F3 says the title, the current character set, then "OK" followed by the name spelled out. It says "capital" for uppercase letters.
* Move with up and down; each key is spoken. Press enter on a character to type it where the cursor is; the character is spoken back.
* Enter on character set switches to the next set, and the new set is spoken.
* Enter on cursor left or cursor right moves the cursor, and the character just after the cursor is spoken, or "end" if the cursor is after the last character.
* Enter on delete removes the character after the cursor, or the last character if the cursor is at the end; the talking F3 says "deleted" and which character.
* Move to OK at any time to hear the whole name, and press enter on it to save. Names can be up to 40 characters; spaces at the start and end are removed. If something is wrong, the F3 shows an error popup, which is spoken.
* The back button leaves without saving.

