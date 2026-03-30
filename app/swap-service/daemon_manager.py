import os
import sys
import signal
import subprocess
import logging
import time
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class DaemonManager:
    def __init__(
        self,
        coind_path: str,
        goldd_path: str,
        oxc_rpc_user: str,
        oxc_rpc_password: str,
        oxg_rpc_user: str,
        oxg_rpc_password: str,
        coind_datadir: str = None,
        goldd_datadir: str = None,
    ):
        self.coind_path = coind_path
        self.goldd_path = goldd_path
        self.oxc_rpc_user = oxc_rpc_user
        self.oxc_rpc_password = oxc_rpc_password
        self.oxg_rpc_user = oxg_rpc_user
        self.oxg_rpc_password = oxg_rpc_password
        self.coind_datadir = coind_datadir
        self.goldd_datadir = goldd_datadir
        self.coind_proc: Optional[subprocess.Popen] = None
        self.goldd_proc: Optional[subprocess.Popen] = None

    def _build_args(
        self,
        daemon_path: str,
        port: int,
        rpc_port: int,
        conf_path: str,
        rpc_user: str,
        rpc_password: str,
        datadir: str = None,
    ) -> List[str]:
        args = [
            daemon_path,
            "-daemon",
            "-server=1",
            "-bind=127.0.0.1",
            "-rpcbind=127.0.0.1",
            "-rpcallowip=127.0.0.1",
            f"-rpcuser={rpc_user}",
            f"-rpcpassword={rpc_password}",
            f"-port={port}",
            f"-rpcport={rpc_port}",
            f"-conf={conf_path}",
        ]
        if datadir:
            args.append(f"-datadir={datadir}")
        return args

    def _write_conf(
        self,
        datadir: str,
        conf_name: str,
        port: int,
        rpc_port: int,
        rpc_user: str,
        rpc_password: str,
    ) -> str:
        conf_path = os.path.join(datadir, f"{conf_name}.conf")
        contents = "\n".join(
            [
                "server=1",
                "daemon=1",
                "listen=1",
                "bind=127.0.0.1",
                "rpcbind=127.0.0.1",
                "rpcallowip=127.0.0.1",
                f"rpcuser={rpc_user}",
                f"rpcpassword={rpc_password}",
                f"port={port}",
                f"rpcport={rpc_port}",
            ]
        )
        with open(conf_path, "w") as f:
            f.write(contents + "\n")
        return conf_path

    def start_daemons(self, testing_mode: bool = False) -> None:
        logger.info("Starting daemons...")

        if not os.path.exists(self.coind_path):
            logger.warning(f"ordexcoind not found at {self.coind_path}")
            return
        if not os.path.exists(self.goldd_path):
            logger.warning(f"ordexgoldd not found at {self.goldd_path}")
            return

        if self.coind_datadir:
            os.makedirs(self.coind_datadir, exist_ok=True)
        if self.goldd_datadir:
            os.makedirs(self.goldd_datadir, exist_ok=True)

        coind_conf = self._write_conf(
            self.coind_datadir,
            "ordexcoin",
            25174,
            25173,
            self.oxc_rpc_user,
            self.oxc_rpc_password,
        )
        goldd_conf = self._write_conf(
            self.goldd_datadir,
            "ordexgold",
            25466,
            25465,
            self.oxg_rpc_user,
            self.oxg_rpc_password,
        )

        coind_args = self._build_args(
            self.coind_path,
            25174,
            25173,
            coind_conf,
            self.oxc_rpc_user,
            self.oxc_rpc_password,
            self.coind_datadir,
        )
        goldd_args = self._build_args(
            self.goldd_path,
            25466,
            25465,
            goldd_conf,
            self.oxg_rpc_user,
            self.oxg_rpc_password,
            self.goldd_datadir,
        )

        logger.info(f"Starting ordexcoind with datadir: {self.coind_datadir}")
        logger.info(f"Starting ordexgoldd with datadir: {self.goldd_datadir}")

        try:
            self.coind_proc = subprocess.Popen(
                coind_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(f"Started ordexcoind (PID: {self.coind_proc.pid})")
        except Exception as e:
            logger.error(f"Failed to start ordexcoind: {e}")

        try:
            self.goldd_proc = subprocess.Popen(
                goldd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(f"Started ordexgoldd (PID: {self.goldd_proc.pid})")
        except Exception as e:
            logger.error(f"Failed to start ordexgoldd: {e}")

        logger.info("Waiting for daemons to initialize...")
        time.sleep(3)

        logger.info("Daemons started successfully")

    def stop_daemons(self) -> None:
        logger.info("Stopping daemons...")

        if self.coind_proc:
            try:
                self.coind_proc.terminate()
                self.coind_proc.wait(timeout=10)
                logger.info("Stopped ordexcoind")
            except Exception as e:
                logger.error(f"Error stopping ordexcoind: {e}")
                try:
                    self.coind_proc.kill()
                except:
                    pass

        if self.goldd_proc:
            try:
                self.goldd_proc.terminate()
                self.goldd_proc.wait(timeout=10)
                logger.info("Stopped ordexgoldd")
            except Exception as e:
                logger.error(f"Error stopping ordexgoldd: {e}")
                try:
                    self.goldd_proc.kill()
                except:
                    pass

    def is_running(self) -> bool:
        return self.coind_proc is not None and self.goldd_proc is not None

    def get_status(self) -> Dict[str, Any]:
        return {
            "ordexcoind_running": self.coind_proc is not None
            and self.coind_proc.poll() is None,
            "ordexgoldd_running": self.goldd_proc is not None
            and self.goldd_proc.poll() is None,
        }
