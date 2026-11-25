"""The few words the panel itself shows, in the user's language. The pixel fonts have no
accents, so the words are written without them."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Words:
    playing: str
    idle: str
    ready: str
    paused: str
    days: tuple[str, ...]
    months: tuple[str, ...]


_WORDS = {
    "en": Words("PLAYING", "NO GAME", "READY", "PAUSED", ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"),
                ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")),
    "es": Words("EN PARTIDA", "SIN JUEGO", "LISTO", "PAUSA", ("LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"),
                ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")),
    "it": Words("IN GIOCO", "NESSUN GIOCO", "PRONTO", "PAUSA", ("LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"),
                ("GEN", "FEB", "MAR", "APR", "MAG", "GIU", "LUG", "AGO", "SET", "OTT", "NOV", "DIC")),
    "de": Words("IM SPIEL", "KEIN SPIEL", "BEREIT", "PAUSE", ("MO", "DI", "MI", "DO", "FR", "SA", "SO"),
                ("JAN", "FEB", "MAR", "APR", "MAI", "JUN", "JUL", "AUG", "SEP", "OKT", "NOV", "DEZ")),
    "pt": Words("JOGANDO", "SEM JOGO", "PRONTO", "PAUSA", ("SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"),
                ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")),
    "fr": Words("EN JEU", "AUCUN JEU", "PRET", "PAUSE", ("LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"),
                ("JAN", "FEV", "MAR", "AVR", "MAI", "JUN", "JUL", "AOU", "SEP", "OCT", "NOV", "DEC")),
}
LANGUAGES = tuple(_WORDS)


def language(value) -> str:
    """"pt-BR" → "pt"; anything unknown falls back to English."""
    code = str(value or "").lower().split("-")[0]
    return code if code in _WORDS else "en"


def words(options: dict | None) -> Words:
    return _WORDS[language((options or {}).get("lang"))]
