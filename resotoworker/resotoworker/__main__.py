from functools import partial
from signal import SIGTERM
import time
import os
import sys
import threading
import resotolib.proc
from typing import List, Dict, Type, Optional, Any
from resotoworker.config import add_config
from resotolib.config import Config
from resotolib.logger import log, setup_logger, add_args as logging_add_args
from resotolib.jwt import add_args as jwt_add_args
from resotolib.baseplugin import BaseActionPlugin, BasePostCollectPlugin, BaseCollectorPlugin, PluginType
from resotolib.web import WebServer
from resotolib.web.metrics import WebApp
from resotolib.utils import log_stats, increase_limits
from resotolib.args import ArgumentParser
from resotolib.core import add_args as core_add_args, resotocore, wait_for_resotocore
from resotolib.core.ca import TLSData
from resotolib.core.actions import CoreActions
from resotolib.core.tasks import CoreTasks
from resotoworker.pluginloader import PluginLoader
from resotoworker.collect import Collector
from resotoworker.cleanup import cleanup
from resotoworker.tag import core_tag_tasks_processor
from resotolib.event import (
    add_event_listener,
    Event,
    EventType,
)
from resotoworker.resotocore import Resotocore
import requests


# This will be used in main() and shutdown()
shutdown_event = threading.Event()
collect_event = threading.Event()


def main() -> None:
    print("   THIS IS A CUSTOM BUILD   ")
    setup_logger("resotoworker")
    # Try to run in a new process group and
    # ignore if not possible for whatever reason
    try:
        os.setpgid(0, 0)
    except Exception:
        pass

    resotolib.proc.parent_pid = os.getpid()

    arg_parser = ArgumentParser(
        description="resoto worker",
        env_args_prefix="RESOTOWORKER_",
    )
    add_args(arg_parser)
    jwt_add_args(arg_parser)
    logging_add_args(arg_parser)
    core_add_args(arg_parser)
    Config.add_args(arg_parser)
    TLSData.add_args(arg_parser)

    # Find resoto Plugins in the resoto.plugins module
    plugin_loader = PluginLoader()
    plugin_loader.add_plugin_args(arg_parser)

    # At this point the CLI, all Plugins as well as the WebServer have
    # added their args to the arg parser
    arg_parser.parse_args()

    # try:
    #     wait_for_resotocore(resotocore.http_uri)
    # except TimeoutError as e:
    #     log.fatal(f"Failed to connect to resotocore: {e}")
    #     sys.exit(1)

    tls_data: Optional[TLSData] = None
    # if resotocore.is_secure:
    #     tls_data = TLSData(
    #         common_name=ArgumentParser.args.subscriber_id,
    #         resotocore_uri=resotocore.http_uri,
    #     )
    #     tls_data.start()
    config = Config(
        ArgumentParser.args.subscriber_id,
        resotocore_uri=resotocore.http_uri,
        tls_data=tls_data,
    )
    add_config(config)
    plugin_loader.add_plugin_config(config)

    import json
    fd = open("config.json", "r")
    custom_config = json.loads(fd.read())
    fd.close()

    config.load_config(provided=custom_config)

    def send_request(request: requests.Request) -> requests.Response:
        # prepared = request.prepare()
        # s = requests.Session()
        # verify = None
        # if tls_data:
        #     verify = tls_data.verify
        # return s.send(request=prepared, verify=verify)
        return requests.Response()

    core = Resotocore(send_request, config)

    collector = Collector(core.send_to_resotocore, config)

    # Handle Ctrl+c and other means of termination/shutdown
    resotolib.proc.initializer()
    add_event_listener(EventType.SHUTDOWN, shutdown, blocking=False)

    # Try to increase nofile and nproc limits
    increase_limits()

    # web_server_args = {}
    # if tls_data:
    #     web_server_args = {
    #         "ssl_cert": tls_data.cert_path,
    #         "ssl_key": tls_data.key_path,
    #     }
    # web_server = WebServer(
    #     WebApp(mountpoint=Config.resotoworker.web_path),
    #     web_host=Config.resotoworker.web_host,
    #     web_port=Config.resotoworker.web_port,
    #     **web_server_args,
    # )
    # web_server.daemon = True
    # web_server.start()

    message = {'kind': 'action', 'message_type': 'collect',
               'data': {'task': '303a991a-1b50-11ed-9557-3285bd250d29', 'step': 'collect'}}
    result = core_actions_processor(plugin_loader, tls_data, collector, message)
    log.info(f"CoreActions Processor returned: {result}")

    # core_actions = CoreActions(
    #     identifier=f"{ArgumentParser.args.subscriber_id}-collector",
    #     resotocore_uri=resotocore.http_uri,
    #     resotocore_ws_uri=resotocore.ws_uri,
    #     actions={
    #         "collect": {
    #             "timeout": Config.resotoworker.timeout,
    #             "wait_for_completion": True,
    #         },
    #         "cleanup": {
    #             "timeout": Config.resotoworker.timeout,
    #             "wait_for_completion": True,
    #         },
    #     },
    #     message_processor=partial(core_actions_processor, plugin_loader, tls_data, collector),
    #     tls_data=tls_data,
    # )

    # task_queue_filter = {}
    # if len(Config.resotoworker.collector) > 0:
    #     task_queue_filter = {"cloud": list(Config.resotoworker.collector)}
    # core_tasks = CoreTasks(
    #     identifier=f"{ArgumentParser.args.subscriber_id}-tagger",
    #     resotocore_ws_uri=resotocore.ws_uri,
    #     tasks=["tag"],
    #     task_queue_filter=task_queue_filter,
    #     message_processor=core_tag_tasks_processor,
    #     tls_data=tls_data,
    # )
    # core_actions.start()
    # core_tasks.start()

    # for Plugin in plugin_loader.plugins(PluginType.ACTION):
    #     assert issubclass(Plugin, BaseActionPlugin)
    #     try:
    #         log.debug(f"Starting action plugin {Plugin}")
    #         plugin = Plugin(tls_data=tls_data)
    #         plugin.start()
    #     except Exception as e:
    #         log.exception(f"Caught unhandled persistent Plugin exception {e}")

    # We wait for the shutdown Event to be set() and then end the program
    # While doing so we print the list of active threads once per 15 minutes
    shutdown(Event(EventType.SHUTDOWN, {"reason": "Complete"}))
    shutdown_event.wait()
    # web_server.shutdown()  # type: ignore
    time.sleep(1)  # everything gets 1000ms to shutdown gracefully before we force it
    resotolib.proc.kill_children(SIGTERM, ensure_death=True)
    log.info("Shutdown complete")
    os._exit(0)


def core_actions_processor(
    plugin_loader: PluginLoader, tls_data: Optional[TLSData], collector: Collector, message: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    collectors: List[Type[BaseCollectorPlugin]] = plugin_loader.plugins(PluginType.COLLECTOR)  # type: ignore
    post_collectors: List[Type[BasePostCollectPlugin]] = plugin_loader.plugins(PluginType.POST_COLLECT)  # type: ignore
    # todo: clean this up
    if not isinstance(message, dict):
        log.error(f"Invalid message: {message}")
        return None
    kind = message.get("kind")
    message_type = message.get("message_type")
    data = message.get("data")
    task_id = data.get("task")  # type: ignore
    log.debug(f"Received message of kind {kind}, type {message_type}, data: {data}")
    if kind == "action":
        try:
            if message_type == "collect":
                start_time = time.time()
                collector.collect_and_send(collectors, post_collectors, task_id=task_id)
                run_time = int(time.time() - start_time)
                log.info(f"Collect ran for {run_time} seconds")
            elif message_type == "cleanup":
                if not Config.resotoworker.cleanup:
                    log.info("Cleanup called but disabled in config" " (resotoworker.cleanup) - skipping")
                else:
                    if Config.resotoworker.cleanup_dry_run:
                        log.info("Cleanup called with dry run configured" " (resotoworker.cleanup_dry_run)")
                    start_time = time.time()
                    cleanup(tls_data=tls_data)
                    run_time = int(time.time() - start_time)
                    log.info(f"Cleanup ran for {run_time} seconds")
            else:
                raise ValueError(f"Unknown message type {message_type}")
        except Exception as e:
            log.exception(f"Failed to {message_type}: {e}")
            reply_kind = "action_error"
        else:
            reply_kind = "action_done"

        reply_message = {
            "kind": reply_kind,
            "message_type": message_type,
            "data": data,
        }
        return reply_message
    return None


def shutdown(event: Event) -> None:
    reason = event.data.get("reason")
    emergency = event.data.get("emergency")

    if emergency:
        resotolib.proc.emergency_shutdown(reason)

    current_pid = os.getpid()
    if current_pid != resotolib.proc.parent_pid:
        return

    if reason is None:
        reason = "unknown reason"
    log.info((f"Received shut down event {event.event_type}:" f" {reason} - killing all threads and child processes"))
    shutdown_event.set()  # and then end the program


def force_shutdown(delay: int = 10) -> None:
    time.sleep(delay)
    log_stats()
    log.error(("Some child process or thread timed out during shutdown" " - forcing shutdown completion"))
    os._exit(0)


def add_args(arg_parser: ArgumentParser) -> None:
    arg_parser.add_argument(
        "--subscriber-id",
        help="Unique subscriber ID (default: resoto.worker)",
        default="resoto.worker",
        dest="subscriber_id",
        type=str,
    )


if __name__ == "__main__":
    main()
