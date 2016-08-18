In order to carry out operations, we can specify Tasks in the resource description.

Tasks have the following keys:
command: The command to run (optional)
container: The container to run (same syntax as long-lived containers)
set-after: A dictionary of key/value pairs that will be set once the command or container terminates succesfully.
unless-set: A key that will prevent the task from executing
only-if-set: A key that must be set before the task executes
lock: A lock that must be held during the run

We consider the following scenarios:
1. A migration that must be executed only once in the cluster:
set-after: done/migration-44
unless-set: done/migration-44
lock: lock/migration-44
nodes: .*

2. A migration that must be executed on every node:
set-after: done/${hostname}/migration-44
unless-set: done/${hostname}/migration-44
lock: lock/${hostname}/migration-44
nodes: .*

3. A migration that must happen after another migration has happened:
set-after: done/migration-45
only-if-set: done/migration-44
nodes: .*


Each host agent does the following on each run:
  For each task in the task list:
    if 'nodes' matches itself:
        if unless-set is given:
            if it's set:
                continue
        if only-if-set is given:
            if it's unset:
                continue
        if lock is set:
            attempt to acquire lock
            if lock acquisition fails:
                continue
        Launch container or run command (inside host agent context...)
        if succesful:
            if set-after is given:
                set keys/values
        release lock if held
