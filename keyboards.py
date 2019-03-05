from telegram import InlineKeyboardButton, KeyboardButton
import constants as c

# this keyboard is not used at the moment
# main_board = [[InlineKeyboardButton("Prognoze", callback_data='prognosis')],
#             [InlineKeyboardButton("Ajutor", callback_data='help'),
#              InlineKeyboardButton("Feedback", callback_data='feedback'),
#              InlineKeyboardButton("Despre noi", callback_data='about')],
#             ]


default_board = [
    [KeyboardButton("/prognosis")],
    [KeyboardButton("/help"), KeyboardButton("/about"), KeyboardButton("/feedback")],
]


def build_route_menu(routes):
    """This constructs a list of buttons to be used in the `routes_board`
    virtual keyboard, which is in turn used in the on-screen keyboard
    for selecting routes.
    :param routes: list of strings, corresponding to route names
    :returns: list corresponding to a keyboard widget"""
    row = []

    for route in routes:
        row.append(InlineKeyboardButton(str(route), callback_data=str(route)))

    return [row]

