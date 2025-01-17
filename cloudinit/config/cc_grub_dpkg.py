# Copyright (C) 2009-2010, 2020 Canonical Ltd.
# Copyright (C) 2012 Hewlett-Packard Development Company, L.P.
#
# Author: Scott Moser <scott.moser@canonical.com>
# Author: Juerg Haefliger <juerg.haefliger@hp.com>
# Author: Matthew Ruffell <matthew.ruffell@canonical.com>
#
# This file is part of cloud-init. See LICENSE file for license information.
"""Grub Dpkg: Configure grub debconf installation device"""

import os
from logging import Logger
from textwrap import dedent

from cloudinit import subp, util
from cloudinit.cloud import Cloud
from cloudinit.config import Config
from cloudinit.config.schema import MetaSchema, get_meta_doc
from cloudinit.settings import PER_INSTANCE
from cloudinit.subp import ProcessExecutionError

MODULE_DESCRIPTION = """\
Configure which device is used as the target for grub installation. This module
should work correctly by default without any user configuration. It can be
enabled/disabled using the ``enabled`` config key in the ``grub_dpkg`` config
dict. The global config key ``grub-dpkg`` is an alias for ``grub_dpkg``. If no
installation device is specified this module will execute grub-probe to
determine which disk the /boot directory is associated with.

The value which is placed into the debconf database is in the format which the
grub postinstall script expects. Normally, this is a /dev/disk/by-id/ value,
but we do fallback to the plain disk name if a by-id name is not present.

If this module is executed inside a container, then the debconf database is
seeded with empty values, and install_devices_empty is set to true.
"""
distros = ["ubuntu", "debian"]
meta: MetaSchema = {
    "id": "cc_grub_dpkg",
    "name": "Grub Dpkg",
    "title": "Configure grub debconf installation device",
    "description": MODULE_DESCRIPTION,
    "distros": distros,
    "frequency": PER_INSTANCE,
    "examples": [
        dedent(
            """\
            grub_dpkg:
              enabled: true
              grub-pc/install_devices: /dev/sda
              grub-pc/install_devices_empty: false
            """
        )
    ],
    "activate_by_schema_keys": [],
}

__doc__ = get_meta_doc(meta)


def fetch_idevs(log):
    """
    Fetches the /dev/disk/by-id device grub is installed to.
    Falls back to plain disk name if no by-id entry is present.
    """
    disk = ""
    devices = []

    try:
        # get the root disk where the /boot directory resides.
        disk = subp.subp(["grub-probe", "-t", "disk", "/boot"], capture=True)[
            0
        ].strip()
    except ProcessExecutionError as e:
        # grub-common may not be installed, especially on containers
        # FileNotFoundError is a nested exception of ProcessExecutionError
        if isinstance(e.reason, FileNotFoundError):
            log.debug("'grub-probe' not found in $PATH")
        # disks from the container host are present in /proc and /sys
        # which is where grub-probe determines where /boot is.
        # it then checks for existence in /dev, which fails as host disks
        # are not exposed to the container.
        elif "failed to get canonical path" in e.stderr:
            log.debug("grub-probe 'failed to get canonical path'")
        else:
            # something bad has happened, continue to log the error
            raise
    except Exception:
        util.logexc(log, "grub-probe failed to execute for grub-dpkg")

    if not disk or not os.path.exists(disk):
        # If we failed to detect a disk, we can return early
        return ""

    try:
        # check if disk exists and use udevadm to fetch symlinks
        devices = (
            subp.subp(
                ["udevadm", "info", "--root", "--query=symlink", disk],
                capture=True,
            )[0]
            .strip()
            .split()
        )
    except Exception:
        util.logexc(
            log, "udevadm DEVLINKS symlink query failed for disk='%s'", disk
        )

    log.debug("considering these device symlinks: %s", ",".join(devices))
    # filter symlinks for /dev/disk/by-id entries
    devices = [dev for dev in devices if "disk/by-id" in dev]
    log.debug("filtered to these disk/by-id symlinks: %s", ",".join(devices))
    # select first device if there is one, else fall back to plain name
    idevs = sorted(devices)[0] if devices else disk
    log.debug("selected %s", idevs)

    return idevs


def handle(
    name: str, cfg: Config, cloud: Cloud, log: Logger, args: list
) -> None:

    mycfg = cfg.get("grub_dpkg", cfg.get("grub-dpkg", {}))
    if not mycfg:
        mycfg = {}

    enabled = mycfg.get("enabled", True)
    if util.is_false(enabled):
        log.debug("%s disabled by config grub_dpkg/enabled=%s", name, enabled)
        return

    idevs = util.get_cfg_option_str(mycfg, "grub-pc/install_devices", None)
    if idevs is None:
        idevs = fetch_idevs(log)

    idevs_empty = mycfg.get("grub-pc/install_devices_empty")
    if idevs_empty is None:
        idevs_empty = not idevs
    elif not isinstance(idevs_empty, bool):
        idevs_empty = util.translate_bool(idevs_empty)
    idevs_empty = str(idevs_empty).lower()

    # now idevs and idevs_empty are set to determined values
    # or, those set by user

    dconf_sel = (
        "grub-pc grub-pc/install_devices string %s\n"
        "grub-pc grub-pc/install_devices_empty boolean %s\n"
        % (idevs, idevs_empty)
    )

    log.debug(
        "Setting grub debconf-set-selections with '%s','%s'"
        % (idevs, idevs_empty)
    )

    try:
        subp.subp(["debconf-set-selections"], dconf_sel)
    except Exception:
        util.logexc(log, "Failed to run debconf-set-selections for grub-dpkg")


# vi: ts=4 expandtab
