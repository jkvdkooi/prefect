from prefect._internal.compatibility.experimental import experiment_enabled
from prefect.cli.root import app
import prefect.settings

# Import CLI submodules to register them to the app
# isort: split

import prefect.cli.agent
import prefect.cli.artifact
import prefect.cli.block
import prefect.cli.cloud
import prefect.cli.concurrency_limit
import prefect.cli.config
import prefect.cli.deployment
import prefect.cli.dev
import prefect.cli.flow
import prefect.cli.flow_run
import prefect.cli.kubernetes
import prefect.cli.server
import prefect.cli.profile
import prefect.cli.work_queue
import prefect.cli.work_pool
import prefect.cli.worker
