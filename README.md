# EU Fuel Prices for Domoticz — v1.0.0

A Python 3 plugin that automatically creates exactly two Custom sensors:

| Unit | Sensor | Unit of measurement |
|---|---|---|
| 1 | Diesel - selected country | €/l |
| 2 | Petrol - selected country | €/l |

Custom sensors are numeric and use Domoticz's native history and graphs.
They are not cumulative counters. History starts at installation; past prices
are not imported. Validated prices are recorded every five minutes, even when
unchanged. History retention and aggregation depend on your Domoticz settings.

## Source and coverage

- EuroOilWatch: https://eurooilwatch.com/api
- Endpoint: https://eurooilwatch.com/api/v1/prices
- Original source: European Commission, Weekly Oil Bulletin:
  https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en

The API is free and requires no account or API key.
Attribution: EuroOilWatch / EC Weekly Oil Bulletin.

Prices are WEEKLY national averages for Euro 95 petrol and diesel, in €/l,
not current prices at individual filling stations. Romania is also shown in
€/l, not RON/l. No currency conversion is performed. Coverage is EU-27,
not all of Europe: the UK, Switzerland, Norway and other non-EU countries
are not available through this endpoint.

## Installation on Raspberry Pi / Linux

Requires Domoticz with Python Plugins support, Python 3 and HTTPS access to
the source. No pip packages, requests or other external Python packages are needed.

1. Extract the archive. Copy the `domoticz-eu-fuel-prices` directory into your
   Domoticz installation's `plugins` directory. For `/home/pi/domoticz`, the
   file must be located at:
   `/home/pi/domoticz/plugins/domoticz-eu-fuel-prices/plugin.py`.
   Avoid an extra nested directory with the same name.
2. Ensure the Domoticz service user can read the files.
3. Restart Domoticz:

   ```bash
   sudo systemctl restart domoticz
   ```

4. In **Setup -> Settings**, temporarily enable **Accept new Hardware Devices /
   Allow new Hardware Devices** (the label depends on your version).
5. In **Setup -> Hardware**, add:
   - Name: `Fuel Prices Romania`
   - Type: `EU Fuel Prices - Petrol and Diesel`
   - Country: `Romania` (or your desired country)
   - API polling interval: `6` hours (default; alternatives: 1, 12, 24)
   - Debug: `No`
   - Data Timeout: `Disabled`, if this field is available;
     the plugin handles data retrieval errors itself.
6. Click **Add**. Both sensors are created automatically with `Used=1`.
   Find them in **Utility**, or **Setup -> Devices**.
   Click each sensor's **Log** button to view its graph.
   Allow a few minutes for the first graph points to appear.

You can disable acceptance of new devices again after both sensors are created.
Do not create Dummy sensors manually or select kWh units or a Counter type.

## Updating from the Romanian edition

Replace `plugin.py` in the existing plugin directory and restart Domoticz.
Do not delete the hardware instance or its sensors. The plugin key, country
codes, device IDs and unit numbers are unchanged, so existing sensors and
history are retained.

Default sensor names created by the Romanian edition are automatically translated
on startup, for example `Motorina - Romania` becomes `Diesel - Romania` and
`Benzina - Romania` becomes `Petrol - Romania`. Country names are translated too.
Device IDs, IDX values and history remain unchanged. Names you customized yourself
are preserved; you can change them using the sensor's Edit action.
You may also rename the hardware instance to `Fuel Prices Romania`.
New installations create sensor names in English automatically.

## Multiple countries and changing country

Add one hardware instance per country. Each creates two sensors with separate
IDX values and graphs. You do not need a separate copy of the plugin for each country.

Changing the country on an existing hardware instance stops updates and logs
an instruction to create a new instance. This prevents mixing different countries'
history. Restore the original country setting to resume updating its sensors.
Custom sensor names and history are preserved across restarts.

## Refresh intervals

| Operation | Interval |
|---|---|
| API request | At startup, then every 6 hours by default |
| Configurable API polling | 1, 6, 12 or 24 hours |
| Sensor updates for graph history | Every 5 minutes, using the latest successfully fetched values |
| Publication of new source prices | Weekly |

**More frequent API requests do not provide daily prices.** The sensors keep
showing the latest weekly national averages until a new bulletin is available.
Periodic sensor updates stop after a failed fetch until retrieval succeeds again.

## Errors and updates

- Fetches at startup, then at the selected interval. Network access runs in a
  separate thread so it does not block the Domoticz heartbeat.
- HTTP timeout: 25 seconds. TLS certificate verification remains enabled.
- On failure, previous values are retained, sensors are marked TimedOut,
  and periodic updates from memory stop until recovery.
  Missing prices are never replaced with zero. On first installation, Domoticz's
  default initial value is not a valid price until the first successful fetch.
- Retries after 5, 10, 20, 40, then 60 minutes.
- Bulletins older than 21 days or with invalid dates are rejected.
- The bulletin date and prices appear in the log. A sensor's update timestamp
  indicates when Domoticz recorded it, not when the price was published.
- The API is an independent service. Changes to its response format or its
  availability may require a plugin update.


Custom Sensor reference:
https://wiki.domoticz.com/Developing_a_Python_plugin
