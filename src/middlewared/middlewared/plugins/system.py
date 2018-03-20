from datetime import datetime
from middlewared.schema import accepts, Bool, Dict, Int, IPAddr, Str
from middlewared.service import ConfigService, no_auth_required, job, Service, ValidationErrors
from middlewared.utils import Popen, sw_version
from middlewared.validators import Range

import os
import socket
import struct
import subprocess
import sys
import sysctl
import time

from OpenSSL import crypto

from licenselib.license import ContractType

# FIXME: Temporary imports until debug lives in middlewared
if '/usr/local/www' not in sys.path:
    sys.path.append('/usr/local/www')
from freenasUI.support.utils import get_license
from freenasUI.system.utils import debug_get_settings, debug_run

# Flag telling whether the system completed boot and is ready to use
SYSTEM_READY = False


class SystemService(Service):

    @no_auth_required
    @accepts()
    async def is_freenas(self):
        """
        Returns `true` if running system is a FreeNAS or `false` is Something Else.
        """
        # This is a stub calling notifier until we have all infrastructure
        # to implement in middlewared
        return await self.middleware.call('notifier.is_freenas')

    @accepts()
    def version(self):
        return sw_version()

    @accepts()
    def ready(self):
        """
        Returns whether the system completed boot and is ready to use
        """
        return SYSTEM_READY

    @accepts()
    async def info(self):
        """
        Returns basic system information.
        """
        uptime = (await (await Popen(
            "env -u TZ uptime | awk -F', load averages:' '{ print $1 }'",
            stdout=subprocess.PIPE,
            shell=True,
        )).communicate())[0].decode().strip()

        serial = (await(await Popen(
            ['dmidecode', '-s', 'system-serial-number'],
            stdout=subprocess.PIPE,
        )).communicate())[0].decode().strip() or None

        product = (await(await Popen(
            ['dmidecode', '-s', 'system-product-name'],
            stdout=subprocess.PIPE,
        )).communicate())[0].decode().strip() or None

        manufacturer = (await(await Popen(
            ['dmidecode', '-s', 'system-manufacturer'],
            stdout=subprocess.PIPE,
        )).communicate())[0].decode().strip() or None

        license = get_license()[0]
        if license:
            license = {
                "system_serial": license.system_serial,
                "system_serial_ha": license.system_serial_ha,
                "contract_type": ContractType(license.contract_type).name.upper(),
                "contract_end": license.contract_end,
            }

        return {
            'version': self.version(),
            'hostname': socket.gethostname(),
            'physmem': sysctl.filter('hw.physmem')[0].value,
            'model': sysctl.filter('hw.model')[0].value,
            'cores': sysctl.filter('hw.ncpu')[0].value,
            'loadavg': os.getloadavg(),
            'uptime': uptime,
            'uptime_seconds': time.clock_gettime(5),  # CLOCK_UPTIME = 5
            'system_serial': serial,
            'system_product': product,
            'license': license,
            'boottime': datetime.fromtimestamp(
                struct.unpack('l', sysctl.filter('kern.boottime')[0].value[:8])[0]
            ),
            'datetime': datetime.utcnow(),
            'timezone': (await self.middleware.call('datastore.config', 'system.settings'))['stg_timezone'],
            'system_manufacturer': manufacturer,
        }

    @accepts(Dict('system-reboot', Int('delay', required=False), required=False))
    @job()
    async def reboot(self, job, options=None):
        """
        Reboots the operating system.

        Emits an "added" event of name "system" and id "reboot".
        """
        if options is None:
            options = {}

        self.middleware.send_event('system', 'ADDED', id='reboot', fields={
            'description': 'System is going to reboot',
        })

        delay = options.get('delay')
        if delay:
            time.sleep(delay)

        await Popen(["/sbin/reboot"])

    @accepts(Dict('system-shutdown', Int('delay', required=False), required=False))
    @job()
    async def shutdown(self, job, options=None):
        """
        Shuts down the operating system.

        Emits an "added" event of name "system" and id "shutdown".
        """
        if options is None:
            options = {}

        self.middleware.send_event('system', 'ADDED', id='shutdown', fields={
            'description': 'System is going to shutdown',
        })

        delay = options.get('delay')
        if delay:
            time.sleep(delay)

        await Popen(["/sbin/poweroff"])

    @accepts()
    @job(lock='systemdebug')
    def debug(self, job):
        # FIXME: move the implementation from freenasUI
        mntpt, direc, dump = debug_get_settings()
        debug_run(direc)
        return dump


class GeneralSystemService(ConfigService):

    class Config:
        datastore = 'system.settings'
        datastore_prefix = 'stg_'

    def __init__(self, *args, **kwargs):
        super(GeneralSystemService, self).__init__(*args, **kwargs)
        self._languages = self.get_system_languages()
        self._time_zones_list = None
        self._kbdmap_choices = None

    def get_system_languages(self):
        LANGUAGES = [
            ('af', 'Afrikaans'),
            ('ar', 'Arabic'),
            ('ast', 'Asturian'),
            ('az', 'Azerbaijani'),
            ('bg', 'Bulgarian'),
            ('be', 'Belarusian'),
            ('bn', 'Bengali'),
            ('br', 'Breton'),
            ('bs', 'Bosnian'),
            ('ca', 'Catalan'),
            ('cs', 'Czech'),
            ('cy', 'Welsh'),
            ('da', 'Danish'),
            ('de', 'German'),
            ('dsb', 'Lower Sorbian'),
            ('el', 'Greek'),
            ('en', 'English'),
            ('en-au', 'Australian English'),
            ('en-gb', 'British English'),
            ('eo', 'Esperanto'),
            ('es', 'Spanish'),
            ('es-ar', 'Argentinian Spanish'),
            ('es-co', 'Colombian Spanish'),
            ('es-mx', 'Mexican Spanish'),
            ('es-ni', 'Nicaraguan Spanish'),
            ('es-ve', 'Venezuelan Spanish'),
            ('et', 'Estonian'),
            ('eu', 'Basque'),
            ('fa', 'Persian'),
            ('fi', 'Finnish'),
            ('fr', 'French'),
            ('fy', 'Frisian'),
            ('ga', 'Irish'),
            ('gd', 'Scottish Gaelic'),
            ('gl', 'Galician'),
            ('he', 'Hebrew'),
            ('hi', 'Hindi'),
            ('hr', 'Croatian'),
            ('hsb', 'Upper Sorbian'),
            ('hu', 'Hungarian'),
            ('ia', 'Interlingua'),
            ('id', 'Indonesian'),
            ('io', 'Ido'),
            ('is', 'Icelandic'),
            ('it', 'Italian'),
            ('ja', 'Japanese'),
            ('ka', 'Georgian'),
            ('kab', 'Kabyle'),
            ('kk', 'Kazakh'),
            ('km', 'Khmer'),
            ('kn', 'Kannada'),
            ('ko', 'Korean'),
            ('lb', 'Luxembourgish'),
            ('lt', 'Lithuanian'),
            ('lv', 'Latvian'),
            ('mk', 'Macedonian'),
            ('ml', 'Malayalam'),
            ('mn', 'Mongolian'),
            ('mr', 'Marathi'),
            ('my', 'Burmese'),
            ('nb', 'Norwegian Bokmål'),
            ('ne', 'Nepali'),
            ('nl', 'Dutch'),
            ('nn', 'Norwegian Nynorsk'),
            ('os', 'Ossetic'),
            ('pa', 'Punjabi'),
            ('pl', 'Polish'),
            ('pt', 'Portuguese'),
            ('pt-br', 'Brazilian Portuguese'),
            ('ro', 'Romanian'),
            ('ru', 'Russian'),
            ('sk', 'Slovak'),
            ('sl', 'Slovenian'),
            ('sq', 'Albanian'),
            ('sr', 'Serbian'),
            ('sr-latn', 'Serbian Latin'),
            ('sv', 'Swedish'),
            ('sw', 'Swahili'),
            ('ta', 'Tamil'),
            ('te', 'Telugu'),
            ('th', 'Thai'),
            ('tr', 'Turkish'),
            ('tt', 'Tatar'),
            ('udm', 'Udmurt'),
            ('uk', 'Ukrainian'),
            ('ur', 'Urdu'),
            ('vi', 'Vietnamese'),
            ('zh-hans', 'Simplified Chinese'),
            ('zh-hant', 'Traditional Chinese'),
        ]
        return LANGUAGES

    async def _initialize_timezones_list(self):
        pipe = os.popen('find /usr/share/zoneinfo/ -type f -not -name zone.tab -not -regex \'.*/Etc/GMT.*\'')
        self._time_zones_list = pipe.read().strip().split('\n')
        self._time_zones_list = [x[20:] for x in self._time_zones_list]
        self._time_zones_list.sort()

    async def get_timezones(self):
        if not self._time_zones_list:
            await self._initialize_timezones_list()
        return self._time_zones_list

    async def _initialize_kbdmap_choices(self):
        """Populate choices from /usr/share/vt/keymaps/INDEX.keymaps"""
        INDEX = "/usr/share/vt/keymaps/INDEX.keymaps"

        if not os.path.exists(INDEX):
            return []
        with open(INDEX, 'rb') as f:
            d = f.read().decode('utf8', 'ignore')
        _all = re.findall(r'^(?P<name>[^#\s]+?)\.kbd:en:(?P<desc>.+)$', d, re.M)
        self._kbdmap_choices = [(name, desc) for name, desc in _all]

    async def get_kbdmap_choices(self):
        if not self._kbdmap_choices:
            await self._initialize_kbdmap_choices()
        return self._kbdmap_choices

    async def get_certificate_fingerprint(self, cert_certificate):
        # getting fingerprint of certificate
        try:
            certificate = crypto.load_certificate(
                crypto.FILETYPE_PEM,
                cert_certificate
            )
        except Exception:
            return None
        else:
            return certificate.digest('sha1').decode()

    async def validate_general_settings(self, data, schema):
        verrors = ValidationErrors()

        kbdmap_choices = await self.get_kbdmap_choices()
        # check

        timezones = await self.get_timezones()
        # check

        syslog_server = data.get('syslogserver')
        if not syslog_server:
            verrors.add(
                f'syslogserver',
                'This field is required'
            )
        else:
            if not re.match("^[\w\.\-]+(\:\d+)?$", syslog_server):
                verrors.add(
                    f'{schema}.syslogserver',
                    'Invalid syslog server format'
                )

        protocol = data.get('guiprotocol')
        if not protocol:
            verrors.add(
                f'{schema}.guiprotocol',
                'This field is required'
            )
        else:
            if protocol != 'http':
                certificate_id = data.get('guicertificate')
                if not certificate_id:
                    verrors.add(
                        f'{schema.guicertificate}',
                        'Protocol has been selected as HTTPS, certificate is required'
                    )
                else:
                    print('\n\nbefore certificate obj')
                    certificate_obj = await self.middleware.call(
                        'datastore.query',
                        'system.certificate',
                        [('id', '=', certificate_id)],
                    )
                    if len(certificate_obj) == 0:
                        verrors.add(
                            f'{schema}.guicertificate',
                            'No matching certificate found in database records, kindly check again'
                        )
                        raise verrors

                    certificate_obj = certificate_obj[0]
                    # getting fingerprint for certificate
                    fingerprint = await self.get_certificate_fingerprint(certificate_obj['cert_certificate'])
                    self.logger.debug('Fingerprint of the certificate used in the GUI: ' + fingerprint)
        return verrors


    @accepts(
        Dict(
            'general_settings',
            IPAddr('guiaddress'),
            Int('guicertificate'),
            Int('guihttpsport', validators=[Range(min=1, max=65535)]),
            Bool('guihttpsredirect'),
            Int('guiport', validators=[Range(min=1, max=65535)]),
            Str('guiprotocol', enum=['http', 'https', 'httphttps']),
            IPAddr('guiv6address'),
            Str('kbdmap'),
            Str('language'),
            Str('sysloglevel', enum=['f_emerg', 'f_alert', 'f_crit', 'f_err', 'f_warning', 'f_notice',
                                     'f_info', 'f_debug', 'f_is_debug']),
            Str('syslogserver'),  # to do only takes ip4 addresses,
            Str('timezone')  # to do
        )
    )
    async def do_update(self, data):
        verrors = await self.validate_general_settings(data, 'general_settings')
        if verrors:
            raise verrors

        config = await self.config()

        new_config = config.copy()
        new_config.update(data)

        await self.middleware.call('datastore.update', 'system.settings', config['id'], new_config, {'prefix': 'stg_'})

        return new_config


async def _event_system_ready(middleware, event_type, args):
    """
    Method called when system is ready, supposed to enable the flag
    telling the system has completed boot.
    """
    global SYSTEM_READY
    if args['id'] == 'ready':
        SYSTEM_READY = True


def setup(middleware):
    middleware.event_subscribe('system', _event_system_ready)
