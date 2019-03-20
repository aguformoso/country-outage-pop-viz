#!/usr/bin/env python
import requests
import sys
import json
import arrow
import pytricia
import datetime
from datetime import timedelta
from collections import defaultdict
from ipaddress import IPv4Network, IPv6Network
from tqdm import tqdm

DEBUG=1
DATE_FMT = "%Y-%m-%dT%H:%M:%S"
APNIC_ECON_URL="http://data1.labs.apnic.net/ipv6-measurement/Economies/%s/%s.asns.json?m=1" % ( sys.argv[1], sys.argv[1] )
START=arrow.get( sys.argv[2] )

def deb( text ):
	if DEBUG==1:
		print >>sys.stderr, text

def to_datetime(string):
	return datetime.datetime.strptime(string, DATE_FMT)
out = {
	'meta': {},
   'isps': []
} 

out['meta']['country'] = sys.argv[1]
out['meta']['start'] = START.strftime(DATE_FMT)
out['meta']['stop'] = arrow.get( arrow.now() ).strftime(DATE_FMT)


r = requests.get( APNIC_ECON_URL )
for thing in r.json():
	pct = thing['percent']
	asn = thing['as']
	name = thing['autnum']
	outages = []
	deb("processing %s" % name )
	deb("processing %s" % asn )
	ro = requests.get( "http://stat.ripe.net/data/prefix-count/data.json?resolution=8h&resource=AS%s&starttime=%s" % (asn, START.strftime("%Y-%m-%dT%H:%M:%S") ) )
	starttime = datetime.datetime.strptime(START.strftime(DATE_FMT), DATE_FMT)
	endtime = starttime + timedelta(hours=8)
	url = "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS{asn}&starttime={starttime}".format(
		asn=asn, starttime=starttime
	)
	announced = requests.get(
		url
	).json()


	py4 = pytricia.PyTricia()
	py6 = pytricia.PyTricia(128)

	for prefix in announced["data"]["prefixes"]:
		prefix_str = str(prefix["prefix"])
		prefix_timelines_ = prefix["timelines"]
		if '.' in prefix_str:
			py4[prefix_str] = prefix_timelines_
		elif ':' in prefix_str:
			py6[prefix_str] = prefix_timelines_


	# Keep only those pfx with no parent
	for py in [py4, py6]:
		for key in py.keys():
			if py.parent(key):
				del py[key]


	timelines = []
	for p in announced["data"]["prefixes"]:

		pfx = p["prefix"]
		if pfx not in py4.keys() and pfx not in py6.keys():
			continue

		pfx = IPv4Network(pfx) if '.' in pfx else IPv6Network(pfx)

		for t in p["timelines"]:
			timelines.append(
				(to_datetime(t["starttime"]), to_datetime(t["endtime"]), pfx.num_addresses)
			)

	_start = starttime  # shared start time
	_end = to_datetime(announced["data"]["latest_time"])
	timeline_count = defaultdict(int)
	hours = 1
	seconds_____hours = (_end - _start).total_seconds() / 60.0 / 60.0 / hours
	bar = tqdm(
		total=seconds_____hours,
		# leave=False,
		desc="{name} (AS{asn})".format(name=name, asn=asn)
	)
	while _start < _end:
		_window_end = _start + timedelta(hours=hours)

		for t0, t1, num_addresses in timelines:
			if t1 <= _start or t0 >= _window_end:
				timeline_count[_start.strftime(DATE_FMT)] += 0
			else:
				timeline_count[_start.strftime(DATE_FMT)] += num_addresses

		bar.update(1)
		_start = _window_end


	j = ro.json()
	v4_series = j['data']['ipv4']
	if v4_series[0]['prefixes'] == 0:
		v4_series = v4_series[1:]
	#if v4_series[-1]['prefixes'] == 0:
	#	v4_series = v4_series[:-1]
	for idx,data in enumerate( v4_series ):
		# 50 {u'prefixes': 16, u'timestamp': u'2017-06-24T16:00:00', u'address-space': 141}
		if data['prefixes'] == 0:
			if len( v4_series ) > idx+1:
				outages.append( [data['timestamp'] , v4_series[idx+1]['timestamp']] )
	out['isps'].append({
		'asn': asn,
		'pct': pct,
		'name': name,
		'outages': outages,
		'timeline': timeline_count
	})

print json.dumps( out, indent=2 )
