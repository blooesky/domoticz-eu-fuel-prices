# -*- coding: utf-8 -*-
"""
<plugin key="EUFuelPrices" name="EU Fuel Prices - Petrol and Diesel" author="4D" version="1.0.0">
    <description>
        <h2>EU fuel prices</h2>
        <p>Two Custom sensors with graphs, in EUR/l. WEEKLY national averages, not station prices.</p>
        <p>Source: EuroOilWatch (https://eurooilwatch.com), based on the EC Weekly Oil Bulletin.</p>
        <p>For another country, add a separate hardware instance to keep its history separate.</p>
    </description>
    <params>
        <param field="Mode1" label="Country" width="220px" required="true" default="RO">
            <options>
                <option label="Austria" value="AT"/>
                <option label="Belgium" value="BE"/>
                <option label="Bulgaria" value="BG"/>
                <option label="Croatia" value="HR"/>
                <option label="Cyprus" value="CY"/>
                <option label="Czechia" value="CZ"/>
                <option label="Denmark" value="DK"/>
                <option label="Estonia" value="EE"/>
                <option label="Finland" value="FI"/>
                <option label="France" value="FR"/>
                <option label="Germany" value="DE"/>
                <option label="Greece" value="GR"/>
                <option label="Hungary" value="HU"/>
                <option label="Ireland" value="IE"/>
                <option label="Italy" value="IT"/>
                <option label="Latvia" value="LV"/>
                <option label="Lithuania" value="LT"/>
                <option label="Luxembourg" value="LU"/>
                <option label="Malta" value="MT"/>
                <option label="Netherlands" value="NL"/>
                <option label="Poland" value="PL"/>
                <option label="Portugal" value="PT"/>
                <option label="Romania" value="RO" default="true"/>
                <option label="Slovakia" value="SK"/>
                <option label="Slovenia" value="SI"/>
                <option label="Spain" value="ES"/>
                <option label="Sweden" value="SE"/>
            </options>
        </param>
        <param field="Mode2" label="API polling interval (hours)" width="100px" default="6">
            <options>
                <option label="1" value="1"/>
                <option label="6" value="6" default="true"/>
                <option label="12" value="12"/>
                <option label="24" value="24"/>
            </options>
        </param>
        <param field="Mode6" label="Debug" width="100px" default="0">
            <options>
                <option label="No" value="0" default="true"/>
                <option label="Yes" value="1"/>
            </options>
        </param>
    </params>
</plugin>
"""

COUNTRIES = {'AT': 'Austria', 'BE': 'Belgium', 'BG': 'Bulgaria', 'HR': 'Croatia', 'CY': 'Cyprus', 'CZ': 'Czechia', 'DK': 'Denmark', 'EE': 'Estonia', 'FI': 'Finland', 'FR': 'France', 'DE': 'Germany', 'GR': 'Greece', 'HU': 'Hungary', 'IE': 'Ireland', 'IT': 'Italy', 'LV': 'Latvia', 'LT': 'Lithuania', 'LU': 'Luxembourg', 'MT': 'Malta', 'NL': 'Netherlands', 'PL': 'Poland', 'PT': 'Portugal', 'RO': 'Romania', 'SK': 'Slovakia', 'SI': 'Slovenia', 'ES': 'Spain', 'SE': 'Sweden'}

import datetime
import json
import math
import queue
import threading
import time
import urllib.request

import Domoticz

# Original labels are retained only to migrate existing default sensor names.
LEGACY_COUNTRIES = {'AT': 'Austria', 'BE': 'Belgia', 'BG': 'Bulgaria', 'HR': 'Croatia', 'CY': 'Cipru', 'CZ': 'Cehia', 'DK': 'Danemarca', 'EE': 'Estonia', 'FI': 'Finlanda', 'FR': 'Franta', 'DE': 'Germania', 'GR': 'Grecia', 'HU': 'Ungaria', 'IE': 'Irlanda', 'IT': 'Italia', 'LV': 'Letonia', 'LT': 'Lituania', 'LU': 'Luxemburg', 'MT': 'Malta', 'NL': 'Tarile de Jos', 'PL': 'Polonia', 'PT': 'Portugalia', 'RO': 'Romania', 'SK': 'Slovacia', 'SI': 'Slovenia', 'ES': 'Spania', 'SE': 'Suedia'}

API_URL = 'https://eurooilwatch.com/api/v1/prices'
MAX_BYTES = 1024 * 1024


def parse_prices(payload, country, today=None):
    """Validate the documented schema. Never substitute missing prices with zero."""
    if not isinstance(payload, dict) or not isinstance(payload.get('countries'), list):
        raise ValueError('API response is missing the countries list')
    bulletin = payload.get('bulletinDate')
    try:
        date = datetime.datetime.strptime(bulletin, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        raise ValueError('Bulletin date is missing or invalid')
    age = ((today or datetime.datetime.now(datetime.timezone.utc).date()) - date).days
    if age < -1 or age > 21:
        raise ValueError('Bulletin is outdated or dated in the future: ' + bulletin)
    rows = [r for r in payload['countries']
            if isinstance(r, dict) and r.get('countryCode') == country]
    if len(rows) != 1:
        raise ValueError('Country is missing or duplicated: ' + country)
    result = {}
    for unit, field in ((1, 'dieselPrice'), (2, 'petrolPrice')):
        raw = rows[0].get(field)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError('Missing or invalid price: ' + field)
        value = float(raw)
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid price: ' + field)
        result[unit] = format(value, '.3f')
    return result, bulletin


def fetch_prices(country, output):
    """Network worker: never call Domoticz or touch Devices in this thread."""
    try:
        request = urllib.request.Request(API_URL, headers={
            'User-Agent': 'Domoticz-EUFuelPrices/1.0.0',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('API response is too large')
        prices, bulletin = parse_prices(json.loads(raw.decode('utf-8-sig')), country)
        output.put((prices, bulletin, None))
    except Exception as exc:
        output.put((None, None, str(exc)))


class BasePlugin:
    def __init__(self):
        self.enabled = False
        self.worker = None
        self.results = queue.Queue()
        self.cached = None
        self.bulletin = None
        self.next_fetch = 0
        self.next_record = 0
        self.failures = 0

    def onStart(self):
        self.country = Parameters.get('Mode1', 'RO')
        if self.country not in COUNTRIES:
            Domoticz.Error('Invalid country: ' + self.country)
            return
        hours = Parameters.get('Mode2', '6')
        self.interval = int(hours) * 3600 if hours in ('1', '6', '12', '24') else 21600
        if Parameters.get('Mode6') == '1':
            Domoticz.Debugging(1)
        # A different country must never overwrite an existing country's graph.
        for unit in (1, 2):
            expected = 'EUFuel-{}-{}'.format(self.country, unit)
            if unit in Devices and Devices[unit].DeviceID != expected:
                Domoticz.Error('Country changed or incompatible device. Add a new hardware instance for the desired country; existing history is preserved.')
                return
        for unit, fuel in ((1, 'Diesel'), (2, 'Petrol')):
            if unit not in Devices:
                Domoticz.Device(
                    Name='{} - {}'.format(fuel, COUNTRIES[self.country]),
                    Unit=unit, DeviceID='EUFuel-{}-{}'.format(self.country, unit),
                    TypeName='Custom', Options={'Custom': '1;€/l'}, Used=1
                ).Create()
            if unit not in Devices:
                Domoticz.Error('Could not create the sensor. Enable Allow new Hardware Devices and restart the hardware instance.')
                return
        # Rename only names generated by the original edition; preserve custom names.
        for unit, old_fuel, fuel in ((1, 'Motorina', 'Diesel'), (2, 'Benzina', 'Petrol')):
            old_name = '{} - {}'.format(old_fuel, LEGACY_COUNTRIES[self.country])
            new_name = '{} - {}'.format(fuel, COUNTRIES[self.country])
            device = Devices[unit]
            prefix = Parameters.get('Name', '') + ' - '
            names = {old_name: new_name, prefix + old_name: prefix + new_name}
            if device.Name in names:
                device.Update(nValue=device.nValue, sValue=device.sValue,
                              Name=names[device.Name])
        self.enabled = True
        Domoticz.Heartbeat(10)
        Domoticz.Log('EU Fuel Prices 1.0.0 | {} | €/l | weekly averages. Source: EuroOilWatch https://eurooilwatch.com / EC Weekly Oil Bulletin'.format(COUNTRIES[self.country]))
        self.onHeartbeat()

    def record(self):
        for unit, value in self.cached.items():
            if unit in Devices:
                # Record unchanged prices too so the graph has a continuous timeline.
                Devices[unit].Update(nValue=0, sValue=value, TimedOut=0)

    def mark_timeout(self):
        for unit in (1, 2):
            if unit in Devices:
                Devices[unit].Update(nValue=Devices[unit].nValue,
                                     sValue=Devices[unit].sValue, TimedOut=1)

    def onHeartbeat(self):
        if not self.enabled:
            return
        now = time.monotonic()
        try:
            prices, bulletin, error = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.worker = None
            if error:
                self.cached = None
                self.failures += 1
                delay = min(3600, 300 * (2 ** min(self.failures - 1, 4)))
                self.next_fetch = now + delay
                self.mark_timeout()
                Domoticz.Error('Fetch failed: {}. Previous values are retained; retrying in {} minutes.'.format(error, delay // 60))
            else:
                changed = prices != self.cached or bulletin != self.bulletin
                self.cached, self.bulletin = prices, bulletin
                self.failures = 0
                self.next_fetch = now + self.interval
                self.record()
                self.next_record = now + 300
                if changed:
                    Domoticz.Log('{} | bulletin {} | Diesel {} €/l | Petrol {} €/l'.format(self.country, bulletin, prices[1], prices[2]))
        if self.cached and now >= self.next_record:
            self.record()
            self.next_record = now + 300
        if self.worker is None and now >= self.next_fetch:
            self.worker = threading.Thread(target=fetch_prices, args=(self.country, self.results), daemon=True)
            self.worker.start()

    def onStop(self):
        self.enabled = False
        # urllib timeout bounds the worker. It owns only its queue, no Domoticz state.


_plugin = BasePlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onHeartbeat():
    _plugin.onHeartbeat()
