"""ECO opening detection from PGN strings."""

from __future__ import annotations

import io

import chess.pgn

# (eco_code, opening_name, list_of_SAN_moves)
# Sorted by move count descending at module level so longest match wins.
_ECO_TABLE: list[tuple[str, str, list[str]]] = sorted(
    [
        # A00–A09: Uncommon Openings
        ("A00", "Polish Opening", ["b4"]),
        ("A00", "Grob Attack", ["g4"]),
        ("A01", "Nimzo-Larsen Attack", ["b3"]),
        ("A02", "Bird Opening", ["f4"]),
        ("A03", "Bird Opening: Dutch Variation", ["f4", "d5"]),
        ("A04", "Reti Opening", ["Nf3"]),
        ("A05", "Reti Opening: King's Indian Attack", ["Nf3", "Nf6"]),
        ("A06", "Reti Opening", ["Nf3", "d5"]),
        ("A07", "Reti Opening: King's Indian Attack", ["Nf3", "d5", "g3"]),
        ("A09", "Reti Opening: Advance Variation", ["Nf3", "d5", "c4"]),

        # A10–A39: English Opening
        ("A10", "English Opening", ["c4"]),
        ("A13", "English Opening: Agincourt Defense", ["c4", "e6"]),
        ("A15", "English Opening: Anglo-Indian Defense", ["c4", "Nf6"]),
        ("A16", "English Opening: Anglo-Indian Defense", ["c4", "Nf6", "Nc3"]),
        ("A20", "English Opening: Reversed Sicilian", ["c4", "e5"]),
        ("A22", "English Opening: Bremen System", ["c4", "e5", "Nc3", "Nf6"]),
        ("A30", "English Opening: Symmetrical Variation", ["c4", "c5"]),
        ("A34", "English Opening: Symmetrical", ["c4", "c5", "Nc3"]),
        ("A36", "English Opening: Symmetrical", ["c4", "c5", "Nc3", "Nc6", "g3"]),

        # A40–A49: Queen's Pawn Openings
        ("A40", "Queen's Pawn Game", ["d4"]),
        ("A41", "Queen's Pawn Game: Old Indian Defense", ["d4", "d6"]),
        ("A43", "Old Benoni", ["d4", "c5"]),
        ("A45", "Trompowsky Attack", ["d4", "Nf6", "Bg5"]),
        ("A46", "Queen's Pawn Game: Torre Attack", ["d4", "Nf6", "Nf3"]),

        # A50–A79: Indian Defenses
        ("A50", "Indian Defense", ["d4", "Nf6"]),
        ("A51", "Budapest Gambit", ["d4", "Nf6", "c4", "e5"]),
        ("A52", "Budapest Gambit", ["d4", "Nf6", "c4", "e5", "dxe5", "Ng4"]),
        ("A53", "Old Indian Defense", ["d4", "Nf6", "c4", "d6"]),
        ("A56", "Benoni Defense", ["d4", "Nf6", "c4", "c5"]),
        ("A57", "Benko Gambit", ["d4", "Nf6", "c4", "c5", "d5", "b5"]),
        ("A60", "Benoni Defense", ["d4", "Nf6", "c4", "c5", "d5", "e6"]),

        # A80–A99: Dutch Defense
        ("A80", "Dutch Defense", ["d4", "f5"]),
        ("A81", "Dutch Defense", ["d4", "f5", "g3"]),
        ("A83", "Dutch Defense: Staunton Gambit", ["d4", "f5", "e4"]),
        ("A85", "Dutch Defense: Queen's Knight Variation", ["d4", "f5", "c4", "Nf6", "Nc3"]),
        ("A87", "Dutch Defense: Leningrad Variation", ["d4", "f5", "c4", "Nf6", "g3", "g6", "Bg2"]),
        ("A90", "Dutch Defense: Classical Variation", ["d4", "f5", "c4", "Nf6", "g3", "e6", "Bg2"]),

        # B00–B19: Sicilian and Semi-Open
        ("B00", "King's Pawn Opening", ["e4"]),
        ("B01", "Scandinavian Defense", ["e4", "d5"]),
        ("B02", "Alekhine Defense", ["e4", "Nf6"]),
        ("B03", "Alekhine Defense: Four Pawns Attack", ["e4", "Nf6", "e5", "Nd5", "d4", "d6", "c4"]),
        ("B06", "Modern Defense", ["e4", "g6"]),
        ("B07", "Pirc Defense", ["e4", "d6", "d4", "Nf6"]),
        ("B09", "Pirc Defense: Austrian Attack", ["e4", "d6", "d4", "Nf6", "Nc3", "g6", "f4"]),
        ("B10", "Caro-Kann Defense", ["e4", "c6"]),
        ("B12", "Caro-Kann Defense", ["e4", "c6", "d4", "d5"]),
        ("B13", "Caro-Kann Defense: Exchange Variation", ["e4", "c6", "d4", "d5", "exd5", "cxd5"]),
        ("B14", "Caro-Kann Defense: Panov-Botvinnik Attack", ["e4", "c6", "d4", "d5", "exd5", "cxd5", "c4"]),
        ("B15", "Caro-Kann Defense: Main Line", ["e4", "c6", "d4", "d5", "Nc3"]),
        ("B17", "Caro-Kann Defense: Steinitz Variation", ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Nd7"]),
        ("B18", "Caro-Kann Defense: Classical Variation", ["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5"]),

        # B20–B99: Sicilian Defense
        ("B20", "Sicilian Defense", ["e4", "c5"]),
        ("B21", "Sicilian Defense: Smith-Morra Gambit", ["e4", "c5", "d4"]),
        ("B22", "Sicilian Defense: Alapin Variation", ["e4", "c5", "c3"]),
        ("B23", "Sicilian Defense: Closed Variation", ["e4", "c5", "Nc3"]),
        ("B27", "Sicilian Defense", ["e4", "c5", "Nf3"]),
        ("B30", "Sicilian Defense: Old Sicilian", ["e4", "c5", "Nf3", "Nc6"]),
        ("B32", "Sicilian Defense: Open Variation", ["e4", "c5", "Nf3", "Nc6", "d4"]),
        ("B33", "Sicilian Defense: Open", ["e4", "c5", "Nf3", "Nc6", "d4", "cxd4", "Nxd4"]),
        ("B34", "Sicilian Defense: Accelerated Dragon", ["e4", "c5", "Nf3", "Nc6", "d4", "cxd4", "Nxd4", "g6"]),
        ("B35", "Sicilian Defense: Accelerated Dragon, Modern Bc4", ["e4", "c5", "Nf3", "Nc6", "d4", "cxd4", "Nxd4", "g6", "Nc3", "Bg7", "Be3", "Nf6", "Bc4"]),
        ("B40", "Sicilian Defense: French Variation", ["e4", "c5", "Nf3", "e6"]),
        ("B41", "Sicilian Defense: Kan Variation", ["e4", "c5", "Nf3", "e6", "d4", "cxd4", "Nxd4", "a6"]),
        ("B44", "Sicilian Defense: Taimanov Variation", ["e4", "c5", "Nf3", "e6", "d4", "cxd4", "Nxd4", "Nc6"]),
        ("B45", "Sicilian Defense: Taimanov", ["e4", "c5", "Nf3", "e6", "d4", "cxd4", "Nxd4", "Nc6", "Nc3"]),
        ("B50", "Sicilian Defense", ["e4", "c5", "Nf3", "d6"]),
        ("B52", "Sicilian Defense: Canal Attack", ["e4", "c5", "Nf3", "d6", "Bb5+"]),
        ("B54", "Sicilian Defense: Open", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4"]),
        ("B56", "Sicilian Defense: Classical Variation", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3"]),
        ("B60", "Sicilian Defense: Richter-Rauzer Variation", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "Nc6", "Bg5"]),
        ("B70", "Sicilian Defense: Dragon Variation", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6"]),
        ("B72", "Sicilian Defense: Dragon Variation", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6", "Be3"]),
        ("B76", "Sicilian Defense: Dragon, Yugoslav Attack", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "g6", "Be3", "Bg7", "f3"]),
        ("B80", "Sicilian Defense: Scheveningen Variation", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "e6"]),
        ("B85", "Sicilian Defense: Scheveningen, Classical", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "e6", "Be2"]),
        ("B90", "Sicilian Defense: Najdorf Variation", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"]),
        ("B92", "Sicilian Defense: Najdorf", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "Be2"]),
        ("B96", "Sicilian Defense: Najdorf", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "Bg5"]),
        ("B97", "Sicilian Defense: Najdorf, Poisoned Pawn", ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6", "Bg5", "e6", "f4", "Qb6"]),

        # C00–C19: French Defense
        ("C00", "French Defense", ["e4", "e6"]),
        ("C01", "French Defense: Exchange Variation", ["e4", "e6", "d4", "d5", "exd5"]),
        ("C02", "French Defense: Advance Variation", ["e4", "e6", "d4", "d5", "e5"]),
        ("C03", "French Defense: Tarrasch Variation", ["e4", "e6", "d4", "d5", "Nd2"]),
        ("C07", "French Defense: Tarrasch, Open Variation", ["e4", "e6", "d4", "d5", "Nd2", "c5", "exd5", "Qxd5"]),
        ("C10", "French Defense: Rubinstein Variation", ["e4", "e6", "d4", "d5", "Nc3"]),
        ("C11", "French Defense: Classical Variation", ["e4", "e6", "d4", "d5", "Nc3", "Nf6"]),
        ("C13", "French Defense: Classical, Albin-Alekhine-Chatard Attack", ["e4", "e6", "d4", "d5", "Nc3", "Nf6", "Bg5", "Be7", "e5"]),
        ("C15", "French Defense: Winawer Variation", ["e4", "e6", "d4", "d5", "Nc3", "Bb4"]),
        ("C16", "French Defense: Winawer", ["e4", "e6", "d4", "d5", "Nc3", "Bb4", "e5"]),
        ("C18", "French Defense: Winawer, Advance", ["e4", "e6", "d4", "d5", "Nc3", "Bb4", "e5", "c5", "a3"]),
        ("C19", "French Defense: Winawer, Advance, Poisoned Pawn", ["e4", "e6", "d4", "d5", "Nc3", "Bb4", "e5", "c5", "a3", "Bxc3+", "bxc3", "Ne7", "Qg4"]),

        # C20–C29: King's Pawn — Open Games
        ("C20", "King's Pawn Game: Open Game", ["e4", "e5"]),
        ("C21", "Center Game", ["e4", "e5", "d4"]),
        ("C22", "Center Game Accepted", ["e4", "e5", "d4", "exd4", "Qxd4"]),
        ("C23", "Bishop's Opening", ["e4", "e5", "Bc4"]),
        ("C25", "Vienna Game", ["e4", "e5", "Nc3"]),
        ("C26", "Vienna Game: Falkbeer Variation", ["e4", "e5", "Nc3", "Nf6"]),
        ("C27", "Vienna Game: Frankenstein-Dracula Variation", ["e4", "e5", "Nc3", "Nf6", "Bc4", "Nxe4"]),
        ("C28", "Vienna Game: Main Line", ["e4", "e5", "Nc3", "Nc6", "Bc4"]),
        ("C29", "Vienna Gambit", ["e4", "e5", "Nc3", "Nf6", "f4"]),

        # C30–C39: King's Gambit
        ("C30", "King's Gambit", ["e4", "e5", "f4"]),
        ("C33", "King's Gambit Accepted", ["e4", "e5", "f4", "exf4"]),
        ("C36", "King's Gambit Accepted: Abbazia Defense", ["e4", "e5", "f4", "exf4", "Nf3", "d5"]),

        # C40–C49: King's Knight Openings
        ("C40", "King's Knight Opening", ["e4", "e5", "Nf3"]),
        ("C41", "Philidor Defense", ["e4", "e5", "Nf3", "d6"]),
        ("C42", "Petrov's Defense", ["e4", "e5", "Nf3", "Nf6"]),
        ("C43", "Petrov's Defense: Stafford Gambit", ["e4", "e5", "Nf3", "Nf6", "Nxe5", "Nc6"]),
        ("C44", "Scotch Game", ["e4", "e5", "Nf3", "Nc6", "d4"]),
        ("C45", "Scotch Game", ["e4", "e5", "Nf3", "Nc6", "d4", "exd4", "Nxd4"]),
        ("C46", "Three Knights Game", ["e4", "e5", "Nf3", "Nc6", "Nc3"]),
        ("C47", "Four Knights Game", ["e4", "e5", "Nf3", "Nc6", "Nc3", "Nf6"]),
        ("C48", "Four Knights Game: Spanish Variation", ["e4", "e5", "Nf3", "Nc6", "Nc3", "Nf6", "Bb5"]),
        ("C49", "Four Knights Game: Double Spanish", ["e4", "e5", "Nf3", "Nc6", "Nc3", "Nf6", "Bb5", "Bb4"]),

        # C50–C59: Italian Game and related
        ("C50", "Italian Game", ["e4", "e5", "Nf3", "Nc6", "Bc4"]),
        ("C51", "Evans Gambit", ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "b4"]),
        ("C52", "Evans Gambit Accepted", ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "b4", "Bxb4"]),
        ("C53", "Italian Game: Classical Variation", ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"]),
        ("C54", "Italian Game: Giuoco Piano", ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3"]),
        ("C55", "Italian Game: Two Knights Defense", ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"]),
        ("C57", "Italian Game: Traxler Counterattack", ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "Bc5"]),
        ("C58", "Italian Game: Two Knights, Morphy Variation", ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "d5", "exd5"]),
        ("C59", "Italian Game: Two Knights, Main Line", ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "d5", "exd5", "Na5"]),

        # C60–C99: Ruy Lopez
        ("C60", "Ruy Lopez", ["e4", "e5", "Nf3", "Nc6", "Bb5"]),
        ("C62", "Ruy Lopez: Old Steinitz Defense", ["e4", "e5", "Nf3", "Nc6", "Bb5", "d6"]),
        ("C63", "Ruy Lopez: Schliemann Defense", ["e4", "e5", "Nf3", "Nc6", "Bb5", "f5"]),
        ("C65", "Ruy Lopez: Berlin Defense", ["e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6"]),
        ("C66", "Ruy Lopez: Berlin Defense, Closed", ["e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6", "O-O", "d6"]),
        ("C67", "Ruy Lopez: Berlin Defense, Open", ["e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6", "O-O", "Nxe4"]),
        ("C68", "Ruy Lopez: Exchange Variation", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Bxc6"]),
        ("C69", "Ruy Lopez: Exchange, Gligoric Variation", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Bxc6", "dxc6", "O-O", "f6"]),
        ("C70", "Ruy Lopez: Morphy Defense", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6"]),
        ("C71", "Ruy Lopez: Noah's Ark Trap", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "d6"]),
        ("C72", "Ruy Lopez: Modern Steinitz Defense", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "d6", "O-O"]),
        ("C77", "Ruy Lopez: Morphy Defense", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6"]),
        ("C78", "Ruy Lopez: Archangelsk Variation", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "b5"]),
        ("C80", "Ruy Lopez: Open Variation", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Nxe4"]),
        ("C84", "Ruy Lopez: Closed Variation", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7"]),
        ("C88", "Ruy Lopez: Closed", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3"]),
        ("C89", "Ruy Lopez: Marshall Attack", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "O-O", "c3", "d5"]),
        ("C92", "Ruy Lopez: Closed, Zaitsev System", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "d6", "c3", "O-O", "h3"]),
        ("C96", "Ruy Lopez: Closed, Chigorin Defense", ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "d6", "c3", "O-O", "h3", "Na5", "Bc2"]),

        # D00–D69: Queen's Gambit and related
        ("D00", "Queen's Pawn Game", ["d4", "d5"]),
        ("D01", "Richter-Veresov Attack", ["d4", "d5", "Nc3", "Nf6", "Bg5"]),
        ("D02", "Queen's Pawn Game: London System", ["d4", "d5", "Nf3", "Nf6", "Bf4"]),
        ("D03", "Queen's Pawn Game: Torre Attack", ["d4", "d5", "Nf3", "Nf6", "Bg5"]),
        ("D04", "Queen's Pawn Game: Colle System", ["d4", "d5", "Nf3", "Nf6", "e3"]),
        ("D06", "Queen's Gambit", ["d4", "d5", "c4"]),
        ("D07", "Queen's Gambit: Chigorin Defense", ["d4", "d5", "c4", "Nc6"]),
        ("D10", "Slav Defense", ["d4", "d5", "c4", "c6"]),
        ("D11", "Slav Defense", ["d4", "d5", "c4", "c6", "Nf3"]),
        ("D12", "Slav Defense: Quiet Variation", ["d4", "d5", "c4", "c6", "Nf3", "Nf6", "e3", "Bf5"]),
        ("D13", "Slav Defense: Exchange Variation", ["d4", "d5", "c4", "c6", "Nf3", "Nf6", "cxd5", "cxd5"]),
        ("D15", "Slav Defense: Main Line", ["d4", "d5", "c4", "c6", "Nf3", "Nf6", "Nc3"]),
        ("D20", "Queen's Gambit Accepted", ["d4", "d5", "c4", "dxc4"]),
        ("D21", "Queen's Gambit Accepted: Normal Variation", ["d4", "d5", "c4", "dxc4", "Nf3"]),
        ("D26", "Queen's Gambit Accepted: Classical", ["d4", "d5", "c4", "dxc4", "Nf3", "Nf6", "e3", "e6"]),
        ("D30", "Queen's Gambit Declined", ["d4", "d5", "c4", "e6"]),
        ("D31", "Queen's Gambit Declined", ["d4", "d5", "c4", "e6", "Nc3"]),
        ("D35", "Queen's Gambit Declined: Exchange Variation", ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "cxd5"]),
        ("D37", "Queen's Gambit Declined: Classical Variation", ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Nf3"]),
        ("D38", "Queen's Gambit Declined: Ragozin Defense", ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Nf3", "Bb4"]),
        ("D43", "Semi-Slav Defense", ["d4", "d5", "c4", "c6", "Nf3", "Nf6", "Nc3", "e6"]),
        ("D44", "Semi-Slav Defense: Botvinnik Variation", ["d4", "d5", "c4", "c6", "Nf3", "Nf6", "Nc3", "e6", "Bg5", "dxc4"]),
        ("D45", "Semi-Slav Defense: Main Line", ["d4", "d5", "c4", "c6", "Nf3", "Nf6", "Nc3", "e6", "e3"]),
        ("D52", "Queen's Gambit Declined: Cambridge Springs Defense", ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Nf3", "c6", "Bg5", "Nbd7", "e3", "Qa5"]),
        ("D53", "Queen's Gambit Declined: Orthodox Defense", ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7"]),
        ("D60", "Queen's Gambit Declined: Orthodox Defense, Main Line", ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O", "Nf3"]),
        ("D63", "Queen's Gambit Declined: Orthodox, Classical", ["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O", "Nf3", "Nbd7", "Rc1"]),

        # D70–D99: Grunfeld Defense
        ("D70", "Grunfeld Defense", ["d4", "Nf6", "c4", "g6", "Nc3", "d5"]),
        ("D76", "Grunfeld Defense: Exchange Variation", ["d4", "Nf6", "c4", "g6", "Nc3", "d5", "cxd5", "Nxd5", "e4", "Nxc3", "bxc3", "Bg7"]),
        ("D80", "Grunfeld Defense", ["d4", "Nf6", "c4", "g6", "Nc3", "d5", "Bg5"]),
        ("D85", "Grunfeld Defense: Exchange Variation", ["d4", "Nf6", "c4", "g6", "Nc3", "d5", "cxd5", "Nxd5"]),
        ("D90", "Grunfeld Defense: Three Knights Variation", ["d4", "Nf6", "c4", "g6", "Nc3", "d5", "Nf3"]),

        # E00–E09: Catalan Opening
        ("E00", "Catalan Opening", ["d4", "Nf6", "c4", "e6", "g3"]),
        ("E04", "Catalan Opening: Open Variation", ["d4", "Nf6", "c4", "e6", "g3", "d5", "Bg2", "dxc4"]),
        ("E06", "Catalan Opening: Closed Variation", ["d4", "Nf6", "c4", "e6", "g3", "d5", "Bg2", "Be7"]),

        # E10–E19: Queen's Indian, Bogo-Indian
        ("E10", "Queen's Indian Defense", ["d4", "Nf6", "c4", "e6", "Nf3"]),
        ("E11", "Bogo-Indian Defense", ["d4", "Nf6", "c4", "e6", "Nf3", "Bb4+"]),
        ("E12", "Queen's Indian Defense", ["d4", "Nf6", "c4", "e6", "Nf3", "b6"]),
        ("E15", "Queen's Indian Defense: Fianchetto Variation", ["d4", "Nf6", "c4", "e6", "Nf3", "b6", "g3"]),
        ("E17", "Queen's Indian Defense: Classical Variation", ["d4", "Nf6", "c4", "e6", "Nf3", "b6", "g3", "Bb7", "Bg2", "Be7"]),

        # E20–E59: Nimzo-Indian Defense
        ("E20", "Nimzo-Indian Defense", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4"]),
        ("E21", "Nimzo-Indian Defense: Three Knights Variation", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "Nf3"]),
        ("E24", "Nimzo-Indian Defense: Saemisch Variation", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "a3", "Bxc3+", "bxc3"]),
        ("E32", "Nimzo-Indian Defense: Classical Variation", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "Qc2"]),
        ("E41", "Nimzo-Indian Defense: Huebner Variation", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "e3", "c5"]),
        ("E43", "Nimzo-Indian Defense: Fischer Variation", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "e3", "b6"]),
        ("E46", "Nimzo-Indian Defense: Reshevsky Variation", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "e3", "O-O"]),
        ("E48", "Nimzo-Indian Defense: Classical, Noa Variation", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "e3", "O-O", "Bd3", "d5"]),
        ("E54", "Nimzo-Indian Defense: Main Line", ["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "e3", "O-O", "Bd3", "d5", "Nf3", "c5"]),

        # E60–E99: King's Indian Defense
        ("E60", "King's Indian Defense", ["d4", "Nf6", "c4", "g6"]),
        ("E61", "King's Indian Defense", ["d4", "Nf6", "c4", "g6", "Nc3"]),
        ("E62", "King's Indian Defense: Fianchetto Variation", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "Nf3", "d6", "g3"]),
        ("E70", "King's Indian Defense: Main Line", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4"]),
        ("E73", "King's Indian Defense: Averbakh Variation", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "Be2", "O-O", "Bg5"]),
        ("E76", "King's Indian Defense: Four Pawns Attack", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "f4"]),
        ("E80", "King's Indian Defense: Saemisch Variation", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "f3"]),
        ("E85", "King's Indian Defense: Saemisch, Orthodox", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "f3", "O-O", "Be3", "e5"]),
        ("E90", "King's Indian Defense: Classical Variation", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "Nf3"]),
        ("E92", "King's Indian Defense: Classical, Petrosian System", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "Nf3", "O-O", "Be2", "e5", "d5"]),
        ("E97", "King's Indian Defense: Mar del Plata Variation", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "Nf3", "O-O", "Be2", "e5", "O-O", "Nc6"]),
        ("E99", "King's Indian Defense: Mar del Plata, Bayonet Attack", ["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "Nf3", "O-O", "Be2", "e5", "O-O", "Nc6", "d5", "Ne7", "b4"]),
    ],
    key=lambda entry: -len(entry[2]),
)


def detect_opening(pgn: str) -> tuple[str | None, str | None]:
    """Detect the ECO opening from a PGN string.

    Returns (eco_code, opening_name) or (None, None) if no match.
    """
    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:
        return None, None

    if game is None:
        return None, None

    # Extract SAN moves from mainline
    moves: list[str] = []
    board = game.board()
    for move in game.mainline_moves():
        moves.append(board.san(move))
        board.push(move)

    if not moves:
        return None, None

    # Match against ECO table (already sorted longest-first)
    for eco_code, name, eco_moves in _ECO_TABLE:
        if len(eco_moves) > len(moves):
            continue
        if moves[: len(eco_moves)] == eco_moves:
            return eco_code, name

    return None, None
