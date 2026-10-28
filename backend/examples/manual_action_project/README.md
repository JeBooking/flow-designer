# Manual action practice

Prepare and start the platform as described in the user guide, then import this entire directory so `workflow.json` and the reference under `assets/` are restored together. This example needs no Python business-project registration, additional business interpreter, or separate worker command.

Start execution and choose Yes at the manual inspection. The conclusion continues to a manual action: simulate the operation yourself using the reference instructions, then choose OK after checking the result. Not OK keeps the same task pending and never advances to Solved; you may choose OK later or recheck an earlier node. Choosing No at inspection leads to escalation.

This is a separate practice workflow with no real equipment. The Cooling example instead uses `confirm`: its simulated Python operation runs once, then waits for the same OK / Not OK confirmation before the automatic report runs.
