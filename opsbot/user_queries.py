"""Some smaller functions that aren't commands, but are used by commands.
"""


def query_users(message, users, level):
    """Return users of the approval level."""
    user_list = []
    for user in users:
        if user["approval_level"] == level:
            user_list.append(user["name"])

    if len(user_list) < 100:
        message.reply("{}".format(", ".join(user_list)))
    elif len(user_list) == 0:
        message.reply("None found.")
    else:
        message.reply("Too many to list ({})!".format(len(user_list)))
