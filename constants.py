VERSION = "1.5"
ICON_BUS = "🚌"

QOS_EXACTLY_ONCE = 2  # MQTT quality of service

STATE_EXPECTING_FEEDBACK = 0
STATE_GOT_FEEDBACK = 1
STATE_EXPECTING_REPLY = 2
STATE_GOT_REPLY = 3


MSG_HELP = "Încearcă comanda `/prognosis 30`. " "Alte comenzi: /feedback, /about."
MSG_SAMPLE = (
    "Iată un exemplu de răspuns la comanda `/prognosis 30`, care arată "
    "timpul de așteptare pentru fiecare stație a rutei 30, care unește "
    "aeroportul cu centrul Chișinăului."
)

MSG_UNSUPPORTED_ROUTE = "Cu regret, nu am informații pentru această rută."
MSG_ABOUT = (
    f"Roata v{VERSION} lucrează pentru binele public. Spune-le și prietenilor tăi despre mine. "
    "Dacă ai întrebări sau sugestii, folosește comanda /feedback. "
    "Pentru a afla despre funcții noi, găsește-ne pe Twitter, @roataway.\n"
    "Datele sunt preluate de pe http://rtec.dekart.com/infodash"
)
MSG_THANKS = (
    "Îți mulțumim! Oamenii noștri cei mai buni în curând vor analiza ceea ce ai scris."
)

MSG_CHOOSE_ROUTE = "Alege ruta:"

MSG_FEEDBACK = "Scrie aici sugestiile sau întrebările tale, și expediază mesajul. Dacă te-ai răzgândit: /cancel"
MSG_FEEDBACK_CANCELLED = "Ehhh.. Ei bine, poate altă dată."
MSG_REPLY = " \nrăspunde apăsând /reply"
MSG_REPLY_HINT = "Scrie aici răspunsul tău. Dacă te-ai răzgândit: /cancel"


MSG_FEEDBACK_NUDGE = "Cauți alte rute? Vrei noi funcționalități? Scrie-ne /feedback."
MSG_CHANGELOG = (
    'Află despre schimbări pe <a href="https://twitter.com/roataway">Twitter @roataway</a>, '
    "sau pe Telegram @roataway."
)
MSG_CREDIT = (
    'Datele sunt preluate de pe <a href="http://rtec.dekart.com/infodash">Infodash</a>.'
)
