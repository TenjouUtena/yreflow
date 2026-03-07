# Commands

## Communication

### say

Send dialogue to everyone in the room.

| Aliases | `say`, `"`, `\u201c`, `\u201d` |
|---------|------|
| Syntax  | `say <message>` or `"<message>` |

```
say Hello there!
"Hello there!
```

### pose

Perform an action or emote in the room (third-person narrative).

| Aliases | `pose`, `:` |
|---------|------|
| Syntax  | `pose <action>` or `:<action>` |

```
pose waves hello
:waves hello
```

### ooc

Send an out-of-character message. Add `:` before the message for pose format.

| Aliases | `ooc`, `>:`, `:>`, `>` |
|---------|------|
| Syntax  | `ooc <message>` or `ooc :<pose>` or `>:<pose>` or `><message>` |

```
ooc This is great!
ooc :nods
>:agrees
>just chatting
```

### whisper

Send a private message to a character in the room.

| Aliases | `w`, `wh` |
|---------|------|
| Syntax  | `w <name>=<message>` |

Modifiers before the message: `:` for pose, `>` for ooc, `:>` for both.

```
w Alice=Hello there!
wh Bob=:waves
w Alice=>ooc message
```

### page

Send a private message (works cross-room).

| Aliases | `p`, `m` |
|---------|------|
| Syntax  | `p <name>=<message>` |

Modifiers before the message: `:` for pose, `>` for ooc.

```
p Alice=Can we talk?
m Bob=:waves from afar
```

### address

Direct speech to a specific character in the room.

| Aliases | `address`, `@` |
|---------|------|
| Syntax  | `address <name>=<message>` or `@<name>=<message>` |

Modifiers before the message: `:` for pose, `>` for ooc.

```
address Alice=This is for you
@Bob=I'm speaking to you
```

## Movement

### go

Move through a named exit.

| Aliases | `go` |
|---------|------|
| Syntax  | `go <exit>` |

```
go north
go through door
```

### home

Teleport to your character's home location.

| Aliases | `home` |
|---------|------|
| Syntax  | `home` |

### teleport

Teleport directly to a named location by its key.

| Aliases | `teleport`, `t` |
|---------|------|
| Syntax  | `teleport <location>` or `t <location>` |

```
t tavern
teleport village
```

## Information

### look

Examine the current room, or a specific character.

| Aliases | `look`, `l` |
|---------|------|
| Syntax  | `look` or `look <name>` |

With no argument, shows the room name, description, exits, and area. With a name, shows that character's details (species, gender, description, tags).

```
look
l Alice
```

### lookup

Search for characters by name across the game.

| Aliases | `lookup` |
|---------|------|
| Syntax  | `lookup <name>` |

Results are displayed in a table showing character name, gender, species, and last online time.    Sends raw name to Wolfery, no matching.

```
lookup zari
```

### laston

Check when a character was last online.

| Aliases | `laston` |
|---------|------|
| Syntax  | `laston <name>` |

```
laston Alice
```

### whereat

Display a tree of population in the current area and sub-areas.

| Aliases | `wa`, `whereat` |
|---------|------|
| Syntax  | `wa` |

## Social

### lead

Start leading a character (they will follow your movements).

| Aliases | `lead` |
|---------|------|
| Syntax  | `lead <name>` |

### follow

Start following a character.

| Aliases | `follow` |
|---------|------|
| Syntax  | `follow <name>` |

### join

Join a group led by another character.

| Aliases | `join` |
|---------|------|
| Syntax  | `join <name>` |

### summon

Request a character to come to your location.

| Aliases | `summon` |
|---------|------|
| Syntax  | `summon <name>` |

### stop follow

Stop following whoever you are currently following.

| Aliases | `stop follow` |
|---------|---------------|
| Syntax  | `stop follow` |

### stop lead

Stop leading characters. With no argument, stops leading everyone. With a name, stops leading that specific character.

| Aliases | `stop lead` |
|---------|-------------|
| Syntax  | `stop lead` or `stop lead <name>` |

```
stop lead
stop lead Alice
```

## Character Management

### profile

Switch to a different character profile/form. With no argument, opens the profile selector. Matches by keyword first, then by name.

| Aliases | `profile`, `morph` |
|---------|------|
| Syntax  | `profile` or `profile <profile-name>` |

```
profile
morph wolf
```

### focus

Highlight a character with a color in the UI.

| Aliases | `focus` |
|---------|------|
| Syntax  | `focus <name>=<color>` |

```
focus Alice=red
```

### unfocus

Remove a character highlight.

| Aliases | `unfocus` |
|---------|------|
| Syntax  | `unfocus <name>` |

## RP

### lfrp

Set your character as looking for roleplay, with a description.

| Aliases | `lfrp` |
|---------|--------|
| Syntax  | `lfrp <description>` |

Characters marked LFRP appear **bold** in the watch list and room panel.

```
lfrp Kitty looking for adventure!
```

### stop lfrp

Clear your LFRP flag.

| Aliases | `stop lfrp` |
|---------|-------------|
| Syntax  | `stop lfrp` |

## Session

### status

Set or clear your character's status message. No argument clears it.

| Aliases | `status` |
|---------|------|
| Syntax  | `status` or `status <text>` |

```
status afk for 5 minutes
status
```

### release

Release/suspend your character (log them out).

| Aliases | `quit`, `sleep` |
|---------|------|
| Syntax  | `quit` or `sleep` |

### sweep

Clear the room view, or sweep a specific character out of the room.

| Aliases | `sweep` |
|---------|------|
| Syntax  | `sweep` or `sweep <name>` |

With no argument, clears the room view. With a name, sweeps that character from the room.

```
sweep
sweep Alice
```

## UI

### settings

Open the settings screen.

| Aliases | `settings` |
|---------|------------|
| Syntax  | `settings` |

### nav

Toggle the navigation panel open or closed.

| Aliases | `nav` |
|---------|-------|
| Syntax  | `nav` |

## Name Matching

Commands that target a character (`whisper`, `page`, `address`, `look`, `lead`, `follow`, `join`, `summon`, `stop lead`, `focus`, `unfocus`, `laston`) use fuzzy name matching:

1. Exact match (case-insensitive)
2. Prefix match

If no match or multiple matches are found, an error is shown.
