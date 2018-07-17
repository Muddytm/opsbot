import random

databases = ["mercury", "venus", "earth", "mars", "jupiter", "saturn",
             "uranus", "neptune"]
users = ["alfred", "bob", "carl", "david", "elvis", "frank", "george", "hank"]
perms = ["readonly", "readwrite"]

times = ["2018-08-01 10:00:00.000000", "2018-08-02 10:00:00.000000",
         "2018-08-03 10:00:00.000000", "2018-08-04 10:00:00.000000",
         "2018-08-05 10:00:00.000000", "2018-08-06 10:00:00.000000"]

reason = "\"a reason\""

for i in range(60):
    db = random.choice(databases)
    user = random.choice(users)
    readonly = random.choice(perms)
    if i < 10:
        time = times[0]
    elif i < 20:
        time = times[1]
    elif i < 30:
        time = times[2]
    elif i < 40:
        time = times[3]
    elif i < 50:
        time = times[4]
    elif i < 60:
        time = times[5]
    print ("{}, {}, {}, {}, {}".format(time, db, user, reason, readonly))
