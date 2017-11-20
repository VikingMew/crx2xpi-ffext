# crx2xpi-ffext
Convert Chrome Web Extensions to Firefox

Major differences between two browsers lies in `manifest.json`. This Flask website automatically converts it to make Chrome extensions compatibble with Firefox. You could deploy it on your own web server so as to avoid the redundancy of Firefox's `web-ext` dependencies and share it with others. However, according to Mozilla's suggestion, developers should avoid providing others with their own API Key/Secret to sign an extension. You can sign for them or let them use at their own risk.

Quite often, migrating to Firefox involves much more than the JSON work. You should use safe JS libraries, like jQuery 2+, in order to meet Mozilla's validation requirements.

## Installation

- Install node.js on the server, and then `npm install --global web-ext`.
- Flask and sqlite3 are required to run the web server.
- Run `app.py dequeue` alongside with `app.py` so as to handle the queue, and run `app.py clear` once every four hours to wipe out-dated files.


## Usage

- POST `/queue` with a file field called `file`:
	-- a `.json` file, to get processed `manifest.json`.
	-- a `.zip` or `.crx` file, to try automatically fetch signed XPI.
	Returns: `id`.

- GET `/queue?id=<id>`: check queue status and result.

- GET `/queue?id=<id>&artifact`: get XPI file if the process was successful. Files will get deleted in 4 hours after generation.

All of above will return a JSON `{"error": "<error message>"}` when errors are encountered.