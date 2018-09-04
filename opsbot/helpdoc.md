# Setup
To set up the Authbot, you'll first want to clone this repository to your server. You'll want to make sure that the bot can run via Python 3.5, and that the following packages are installed for the bot to use: slackbot, requests, pyodbc, and pyyaml. You'll want to setup the config.py as described in this repo's README as well. Some things aren't covered yet, come and yell at me if something is breaking. :)

# Granting Database Access
To gain access to a database, go to the main Authbot channel and type `grant [database] [reason]`. If you want read-write access, type `grantrw` instead of `grant`. You must also be approved before you can get access. Examples: `grant cooldb Testing`, `grantrw radicaldb Just messing around`

# Extending Database Access
To extend access to a database, go to the main Authbot channel and type `grant [database]`. No specified reason is necessary.

# Database Details
To get database details (server name and current users with access), message Authbot with `dbdetails [database]`.

# Getting Approval
To get approval for the purposes of obtaining database access, send `approve me` in a direct message to the Authbot. The admins will be asked to approve or deny your request, and you will be informed when they've responded.
