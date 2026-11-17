"""Generates the public DEMO show "The Last Reel" - an ORIGINAL, fictional microdrama written for this
project (no real show, no company data). Output: demo/scripts/the_last_reel/episode-NN.txt in the same
screenplay format as the real input pack (EPISODE LOGLINE header, SCENE blocks, Start/End times).

    python demo/make_demo_show.py

Times are computed here from each block's length, so they are consistent and exact."""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "scripts" / "the_last_reel"

# Each block: (kind, who/delivery, text). kind: C camera, A action, S sound fx, D dialogue ("NAME|delivery").
EPISODES = [
    ("Maya Reyes, a night-shift film archivist at Hale Pictures, finds an unlabelled reel carrying her missing "
     "father's name; studio head Victor Hale walks in and demands it.",
     [("INT. HALE PICTURES ARCHIVE VAULT - NIGHT", [
        ("C", "", "Slow push through rows of steel film cans glowing under a single work lamp."),
        ("A", "", "Maya threads an old reel onto the restoration bench, gloves on, breath fogging in the cold vault."),
        ("S", "", "The projector motor coughs, then hums."),
        ("D", "MAYA|whispering", "Can 4417. No title, no date. Who hides a film down here?"),
        ("A", "", "She turns the can over. A strip of masking tape reads: PROPERTY OF THOMAS REYES."),
        ("D", "MAYA|stunned", "Dad?"),
        ("C", "", "Close on Maya's trembling hand over the faded handwriting."),
        ("D", "MAYA|shaken", "Twenty years. They told us there was nothing left of him. Not one frame."),
        ("S", "", "The vault door slams. Footsteps on concrete."),
        ("D", "VICTOR|cold, controlled", "That can is not on your restoration list, Miss Reyes."),
        ("A", "", "Victor Hale steps into the lamp light, silver hair, black overcoat, two security guards behind him."),
        ("D", "MAYA|defensive", "It was misfiled. I was logging it."),
        ("D", "VICTOR|quietly", "Give it to me."),
        ("D", "MAYA|steady", "It has my father's name on it."),
        ("D", "VICTOR|smiling thinly", "Your father stole from this studio. Everything he touched belongs to me."),
        ("A", "", "Victor nods. A guard grabs Maya's wrist and twists the reel out of her hands."),
        ("D", "MAYA|in pain", "Let go of me!"),
        ("D", "VICTOR|to the guards", "She's finished here. Escort her out. And take her keycard."),
      ]),
      ("INT. ARCHIVE CORRIDOR - CONTINUOUS", [
        ("A", "", "The guards march Maya down the corridor. She glances back."),
        ("C", "", "Through the vault window: Victor alone, holding the reel up to the light."),
        ("A", "", "Victor's face drains of colour as he reads the frames."),
        ("D", "VICTOR|under his breath", "He filmed it. That fool actually filmed it."),
        ("A", "", "He lowers the reel. In the frame, frozen: a younger Victor standing beside a burning door."),
      ])]),
    ("Thrown out of the studio, Maya is stopped in the rain by Daniel Hale, Victor's son, who has taken the reel "
     "from his father's office and wants to know what it hides.",
     [("EXT. HALE PICTURES GATE - NIGHT - RAIN", [
        ("A", "", "Rain hammers the studio gate. A guard shoves Maya onto the wet pavement and tosses her bag after her."),
        ("D", "GUARD|sneering", "Mr Hale says you're lucky he isn't calling the police."),
        ("D", "MAYA|furious", "Tell Mr Hale I know what's on that reel."),
        ("S", "", "A car engine. Headlights sweep across Maya's face."),
        ("A", "", "A black sedan stops. The window lowers: Daniel Hale, Victor's son."),
        ("D", "DANIEL|calm", "Get in. You'll catch pneumonia arguing with a gate."),
        ("D", "MAYA|wary", "You're his son. Why would I trust you?"),
        ("A", "", "Daniel lifts a film can from the passenger seat. Can 4417."),
        ("D", "DANIEL|serious", "Because I took this from his desk ten minutes ago."),
        ("D", "MAYA|shocked", "You stole from your own father?"),
      ]),
      ("INT. DANIEL'S CAR - MOVING - NIGHT", [
        ("C", "", "Wipers beat. Streetlights slide across their faces."),
        ("D", "DANIEL|quiet", "I've never seen him afraid. Tonight he locked himself in his office and burned papers."),
        ("D", "MAYA|tense", "Then you know he's hiding something."),
        ("D", "DANIEL|hesitant", "I know he called someone and said one sentence. The Reyes girl has seen it."),
        ("A", "", "Maya's phone lights up. Unknown number. A text: GIVE BACK THE REEL OR YOUR MOTHER'S HOUSE BURNS TOO."),
        ("D", "MAYA|terrified", "Too? What does he mean, too?"),
        ("A", "", "Daniel swerves to the kerb and stares at the message."),
        ("D", "DANIEL|grim", "The old studio fire. The one where your father disappeared."),
      ])]),
    ("Ruth Okafor, an old projectionist and Maya's mentor, screens the reel: it shows the studio fire twenty "
     "years ago and a man locking a door from outside.",
     [("INT. RIALTO CINEMA - PROJECTION BOOTH - NIGHT", [
        ("C", "", "Dust floats in the beam of a vintage projector."),
        ("A", "", "Ruth Okafor, seventy, threads Can 4417 with practised hands while Maya and Daniel watch."),
        ("D", "RUTH|gruff", "Nitrate stock. If this catches, the whole booth goes up in seconds. Nobody breathes on it."),
        ("S", "", "The projector clatters to life."),
        ("C", "", "On the small screen: grainy footage of the old Hale studio lot at night."),
        ("D", "MAYA|whispering", "That's the old sound stage. The one that burned."),
        ("A", "", "On screen, flames climb the stage wall. A man in a long coat chains the fire door shut."),
        ("D", "DANIEL|horrified", "Someone locked them in."),
        ("A", "", "Ruth stops the projector on a single frame. The man's hand: a heavy signet ring."),
        ("D", "RUTH|very still", "I know that ring. I've seen it on one man for forty years."),
        ("D", "MAYA|barely audible", "Say it."),
      ]),
      ("INT. RIALTO CINEMA - PROJECTION BOOTH - CONTINUOUS", [
        ("D", "RUTH|slowly", "Victor Hale."),
        ("A", "", "Daniel steps back from the screen as if struck."),
        ("D", "DANIEL|breaking", "No. My father was a producer, not a murderer."),
        ("S", "", "Downstairs, the cinema's front door bangs open."),
        ("D", "RUTH|urgent", "Were you followed?"),
        ("A", "", "Footsteps race up the stairs. The booth door handle begins to turn."),
      ])]),
    ("At the Hale Pictures anniversary gala, Maya confronts Victor in public; Lena Hale humiliates her, Daniel "
     "defends her, and Victor accuses Maya of theft in front of the press.",
     [("INT. HALE PICTURES GALA - BALLROOM - NIGHT", [
        ("C", "", "Crystal chandeliers, cameras flashing, a giant banner: HALE PICTURES, FIFTY YEARS OF STORIES."),
        ("A", "", "Maya, in a borrowed black dress, walks straight through the crowd toward the stage."),
        ("D", "LENA|mocking", "Look who crawled in. The archive girl my father fired for stealing."),
        ("A", "", "Lena Hale, Victor's daughter, tips a glass of champagne down the front of Maya's dress."),
        ("S", "", "Laughter ripples through the guests."),
        ("D", "LENA|sweetly", "Oops. Now you look like what you are."),
        ("D", "DANIEL|sharp", "Enough, Lena."),
        ("A", "", "Daniel steps between them and offers Maya his jacket. The room goes quiet."),
        ("D", "LENA|stunned", "You're taking her side? Over family?"),
        ("D", "DANIEL|steady", "I'm taking the side of the truth."),
        ("A", "", "On stage, Victor taps the microphone. Every camera turns to him."),
        ("D", "VICTOR|warm, public voice", "Friends. Tonight we celebrate fifty years. And tonight, sadly, a thief is in this room."),
        ("A", "", "A spotlight swings onto Maya."),
        ("D", "VICTOR|pointing", "That woman stole a priceless reel from my archive. Officers, please."),
        ("A", "", "Two police officers push through the crowd toward Maya. Cameras flash in her face."),
        ("D", "MAYA|loud, defiant", "Ask him what's on the reel! Ask him who chained the fire door!"),
        ("A", "", "Victor's smile does not move. But his hand closes into a fist around the microphone."),
      ])]),
    ("Arrested after the gala, Maya meets Inspector Kwame Osei, who reveals that her father's case was closed "
     "on orders from above - and that Thomas Reyes was seen alive three years ago.",
     [("INT. CENTRAL POLICE STATION - INTERVIEW ROOM - NIGHT", [
        ("C", "", "A bare table, a buzzing light, Maya alone with champagne still drying on her dress."),
        ("A", "", "Inspector Kwame Osei enters with a thick, dusty case file and drops it on the table."),
        ("D", "OSEI|tired", "Thomas Reyes. Missing, presumed dead in the Hale studio fire. Case closed in nine days."),
        ("D", "MAYA|bitter", "Nine days. For seven people."),
        ("D", "OSEI|low", "Closed on orders from the deputy commissioner. Who played golf every Sunday with Victor Hale."),
        ("A", "", "Maya looks up sharply."),
        ("D", "MAYA|suspicious", "Why are you telling me this?"),
        ("D", "OSEI|leaning in", "Because tonight Hale asked me to lose you in the system. And I don't like being told what to lose."),
        ("A", "", "Osei slides a grainy photograph across the table: a grey-bearded man at a ferry terminal."),
        ("D", "OSEI|quiet", "Border camera. Three years ago."),
        ("C", "", "Close on the photograph. The man's face. Maya's face, thirty years older."),
        ("D", "MAYA|breathless", "That's impossible."),
        ("D", "OSEI|certain", "Your father isn't dead, Miss Reyes. He walked out of that fire."),
        ("S", "", "The door bursts open."),
        ("D", "VICTOR|icy", "Inspector. My lawyer would like a word with you. Outside."),
      ])]),
    ("Daniel discovers forty frames are missing from the reel and finds them in Victor's private safe; Victor "
     "catches him and disowns him.",
     [("INT. VICTOR'S STUDY - HALE MANSION - NIGHT", [
        ("A", "", "Daniel kneels at a wall safe behind a framed film poster, a stethoscope pressed to the dial."),
        ("D", "DANIEL|muttering", "Forty frames cut out of the reel. If he kept anything, he kept it here."),
        ("S", "", "Click. The safe swings open."),
        ("A", "", "Inside: a small film tin labelled 4417-B. Beside it, a passport with a stranger's name and Thomas Reyes's face."),
        ("D", "DANIEL|stunned", "He knew. He's known where Reyes was all along."),
        ("A", "", "Daniel opens the tin. He holds a strip of frames to the desk lamp."),
        ("C", "", "In the frames: Victor at the fire door, turning to look straight at the camera."),
        ("S", "", "A lamp switches on behind him."),
        ("D", "VICTOR|softly", "You always were the curious one."),
        ("A", "", "Victor stands in the doorway in a dressing gown, a glass of whisky in his hand."),
        ("D", "DANIEL|shaking", "Seven people died in that fire. You chained the door."),
        ("D", "VICTOR|calm", "I built this family on that fire. Your school, your car, your name."),
        ("D", "DANIEL|furious", "Then I don't want any of it."),
        ("D", "VICTOR|cold", "Put the frames down, Daniel. Choose carefully."),
        ("A", "", "Daniel pockets the film strip."),
        ("D", "VICTOR|final", "Then from tonight, you are not my son."),
      ])]),
    ("Victor orders the old archive emptied by fire; Maya and Ruth are trapped inside, Daniel breaks them out, "
     "and the security footage shows a living man in the archive.",
     [("INT. HALE PICTURES OLD ARCHIVE - NIGHT", [
        ("A", "", "Maya and Ruth search the shelves of the abandoned archive by torchlight."),
        ("D", "RUTH|urgent", "If your father hid a second reel, it's in the nitrate room. He never trusted anyone else's shelves."),
        ("S", "", "Behind them, a heavy door slams. A chain rattles through the handles."),
        ("A", "", "Maya runs back and pulls the door. It won't move."),
        ("D", "MAYA|panicking", "Someone chained it. From outside."),
        ("S", "", "A crackle. The smell of smoke rolls under the door."),
        ("D", "RUTH|grim", "Same door. Same trick. He's doing it again."),
        ("A", "", "Smoke pours through the vents. Ruth coughs and sinks to her knees."),
        ("D", "MAYA|desperate", "Ruth, stay with me. Stay low!"),
        ("S", "", "Metal shrieks. Bolt cutters bite through the chain."),
        ("A", "", "The door crashes open. Daniel, soot on his face, hauls Ruth over his shoulder."),
        ("D", "DANIEL|shouting", "Go! The roof's coming down!"),
      ]),
      ("EXT. OLD ARCHIVE - NIGHT", [
        ("A", "", "They stumble into the night as the archive roof collapses behind them."),
        ("A", "", "Daniel hands Maya a security tablet he grabbed from the guard booth."),
        ("D", "DANIEL|breathless", "The cameras were still recording. Look at the nitrate room."),
        ("C", "", "On the tablet: a grey-bearded man in the smoke, clutching a film can, slipping out a side door."),
        ("D", "MAYA|whispering", "He was in there. My father was in there tonight."),
      ])]),
    ("At the Hale Pictures premiere, Maya screens the restored reel to the press; Victor's crime plays on the big "
     "screen, Thomas Reyes appears, and Victor makes one last move.",
     [("INT. HALE PICTURES PREMIERE THEATRE - NIGHT", [
        ("C", "", "A packed premiere. Press in every row. Victor in the front seat, smiling for the cameras."),
        ("A", "", "The lights dim. Instead of the trailer, grainy footage fills the giant screen: the burning sound stage."),
        ("S", "", "A gasp runs through the audience."),
        ("A", "", "On screen, the man in the long coat chains the fire door, then turns. Victor's younger face, enormous."),
        ("D", "VICTOR|on his feet, shouting", "Stop this! Turn it off!"),
        ("A", "", "In the projection booth window above, Maya and Ruth keep the reel running."),
        ("D", "MAYA|over the speakers", "Seven people. Twenty years. Everyone in this room should see it."),
        ("A", "", "Inspector Osei walks down the aisle toward Victor with two officers."),
        ("D", "OSEI|formal", "Victor Hale, you're under arrest for the murders at Stage Nine."),
        ("A", "", "Victor backs away. A side door opens. A grey-bearded man steps into the projector beam."),
        ("D", "THOMAS|hoarse", "Hello, Victor. You missed me."),
        ("A", "", "Maya freezes in the booth window."),
        ("D", "MAYA|tears in her voice", "Dad?"),
        ("A", "", "Victor grabs a gun from an officer's holster and turns it on the projection booth."),
        ("D", "VICTOR|wild", "Stop the reel, Maya. Or this is the last thing your father ever watches."),
      ])]),
]

DUR = {"C": 2.4, "A": 3.6, "S": 1.8}


def duration(kind: str, text: str) -> float:
    if kind == "D":
        return round(max(1.6, len(text.split()) / 2.7 + 0.5), 2)
    return round(DUR[kind] + len(text.split()) * 0.04, 2)


def ts(s: float) -> str:
    m, sec = divmod(s, 60)
    return f"{int(m):02d}:{sec:05.2f}"


def build() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "show_info.yaml").write_text(
        'show: "The Last Reel (demo)"\n'
        'source: "Original fictional microdrama written for the public demo - not a real show"\n'
        "language: en\n", encoding="utf-8")
    paths = []
    for n, (logline, scenes) in enumerate(EPISODES, 1):
        t = 0.0
        out = [f"EPISODE NUMBER: Episode {n}", f"EPISODE LOGLINE: {logline}",
               "CONTINUITY NOTES: Original demo show for AI Promo Intelligence Studio.", "", "--- SCRIPT START ---", ""]
        for si, (heading, blocks) in enumerate(scenes, 1):
            out += [f"SCENE {si:02d}", f"Scene heading: {heading}", f"Scene start: {ts(t)}", ""]
            for kind, who, text in blocks:
                d = duration(kind, text)
                label = {"C": "CAMERA", "A": "ACTION", "S": "SOUND FX"}.get(kind)
                if kind == "D":
                    name, delivery = who.split("|")
                    label = f"{name} ({delivery.capitalize()})"
                    text = f"\"{text}\""
                out += [f"**{label}:**", f"Start: ({ts(t)}) | End: ({ts(t + d)})", text, ""]
                t = round(t + d + 0.15, 2)
            out += [f"Scene end: {ts(t)}", ""]
        out += ["--- SCRIPT END ---", ""]
        p = OUT / f"episode-{n:02d}.txt"
        p.write_text("\n".join(out), encoding="utf-8")
        paths.append(p)
    return paths


if __name__ == "__main__":
    for p in build():
        print(p.name)
