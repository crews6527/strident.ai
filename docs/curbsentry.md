# Optional CurbSentry monitor

This release extends the supplied independent Strident RC2 desktop package with a read-only CurbSentry page. It does not import CurbSentry or the legacy MARK plugin. Its existing store, memory and task flows remain in the package.

Run Install-Strident.cmd in this new folder, then Launch-Strident.cmd. Start the separate CurbSentry service first. Open CurbSentry in Strident's sidebar, choose Connect and select `%LOCALAPPDATA%\CurbSentryPrivate\strident-bridge.json`. Choose Start monitoring. Monitoring starts off every launch and stops when the window closes.

The connection file is private. It contains a reader key and a loopback address. It cannot retrieve video, read the full CurbSentry database, edit records or acknowledge alerts. The adapter has bounded response size, a three-second wall-clock request deadline and no automatic model calls. It checks every fifteen seconds only while enabled and does not overlap reads.

New confirmed repeat-sighting alerts appear on the CurbSentry page and produce a console notice, sidebar badge and window attention request. Already notified alert IDs are saved in Strident's data directory. Review and mark alerts reviewed in CurbSentry; reviewed or withdrawn alerts leave the reader queue. This release does not send mobile push, email or text notifications.

Python/Qt automated checks and idle measurement were run on Linux. Native Windows attention, process shutdown, launchers and connection setup still need validation on the actual computer. This is an opt-in release candidate, not a verified repair of the previous MARK integration. The old plugin adapter and its process logs were not included in the supplied Curb archive, so the earlier conflict's cause remains unconfirmed.
