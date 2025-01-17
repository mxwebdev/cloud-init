# Copyright (C) 2019-2020 Gonéri Le Bouder
#
# This file is part of cloud-init. See LICENSE file for license information.

import os
import platform

import cloudinit.distros.netbsd
from cloudinit import log as logging
from cloudinit import subp, util

LOG = logging.getLogger(__name__)


class Distro(cloudinit.distros.netbsd.NetBSD):
    hostname_conf_fn = "/etc/myname"
    init_cmd = ["rcctl"]

    def _read_hostname(self, filename, default=None):
        return util.load_file(self.hostname_conf_fn)

    def _write_hostname(self, hostname, filename):
        content = hostname + "\n"
        util.write_file(self.hostname_conf_fn, content)

    def _get_add_member_to_group_cmd(self, member_name, group_name):
        return ["usermod", "-G", group_name, member_name]

    def manage_service(self, action: str, service: str):
        """
        Perform the requested action on a service. This handles OpenBSD's
        'rcctl'.
        May raise ProcessExecutionError
        """
        init_cmd = self.init_cmd
        cmds = {
            "stop": ["stop", service],
            "start": ["start", service],
            "enable": ["enable", service],
            "restart": ["restart", service],
            "reload": ["restart", service],
            "try-reload": ["restart", service],
            "status": ["check", service],
        }
        cmd = list(init_cmd) + list(cmds[action])
        return subp.subp(cmd, capture=True)

    def lock_passwd(self, name):
        try:
            subp.subp(["usermod", "-p", "*", name])
        except Exception:
            util.logexc(LOG, "Failed to lock user %s", name)
            raise

    def unlock_passwd(self, name):
        pass

    def _get_pkg_cmd_environ(self):
        """Return env vars used in OpenBSD package_command operations"""
        os_release = platform.release()
        os_arch = platform.machine()
        e = os.environ.copy()
        e["PKG_PATH"] = (
            "ftp://ftp.openbsd.org/pub/OpenBSD/{os_release}/"
            "packages/{os_arch}/"
        ).format(os_arch=os_arch, os_release=os_release)
        return e


# vi: ts=4 expandtab
