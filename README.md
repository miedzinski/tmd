# ToMojDom Notifier

This script lets you receive notifications in a Discord channel when there are new settlements or payments recorded for your property on ToMojDom.pl.

## How it works

Each ToMojDom.pl account is managed by a separate JSON file in the `db/` directory. To add a new account, create a `.json` file in the `db` directory like this:

```json
{
    "username": "<your username>",
    "password": "<your password>"
}
```

Run the script (for example, with [uv](https://github.com/astral-sh/uv)):

```sh
uv run tmd.py
```

On the first run, the script will download all settlements and payments, but won't send notifications (to avoid spamming). For future runs, add your Discord webhook URL to the JSON file:

```json
{
    "username": "<your username>",
    "password": "<your password>",
    "discord_webhook_url": "<your webhook url>"
    // ...settlements and payments omitted
}
```

More info about Discord webhooks: https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks

## Deployment

This script is designed to be "local-first" - it saves already seen settlements and payments in local JSON files. You can keep the database in git and run the script on a schedule using the provided GitHub Actions workflow.

To deploy:
- Fork this repository
- **Set your fork to private** (your account data is stored in the repo)
- Add your account JSON files to the `db/` directory
- Make sure the workflow is enabled (it might be disabled in forks)

That's it!

## License

The code is licensed under the [Unlicense](LICENSE).
