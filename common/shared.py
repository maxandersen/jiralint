import urllib
import urllib2
import base64
import json

def jiraquery (options, url):
    request = urllib2.Request(options.jiraserver + url)
    base64string = base64.encodestring('%s:%s' % (options.username, options.password)).replace('\n', '')
    request.add_header("Authorization", "Basic %s" % base64string)   


    if options.verbose:
        print "Query: " + options.jiraserver + url
   
    return json.load(urllib2.urlopen(request))

def jirapost(options, url, data):
    if(options.verbose):
        handler=urllib2.HTTPSHandler(debuglevel=1)
    else:
        handler=urllib2.HTTPSHandler()
        
    opener = urllib2.build_opener(handler)
    urllib2.install_opener(opener)

    jdata = json.dumps(data)
    
    request = urllib2.Request(options.jiraserver + url,jdata)
    base64string = base64.encodestring('%s:%s' % (options.username, options.password)).replace('\n', '')
    request.add_header("Authorization", "Basic %s" % base64string)   
    request.add_header("Content-Type","application/json")

    if options.verbose:
        print "Post: " + options.jiraserver + url
        print "Data: " + jdata

    response = ''
    
    try: 
        response = urllib2.urlopen(request)
    except urllib2.HTTPError, e:
        print('HTTPError = ' + str(e.code) + ' ' + e.read())
        raise(e)

    return json.load(response)
    
def jiraupdate(options, url, data):
    if(options.verbose):
        handler=urllib2.HTTPSHandler(debuglevel=1)
    else:
        handler=urllib2.HTTPSHandler()
        
    opener = urllib2.build_opener(handler)
    urllib2.install_opener(opener)

    jdata = json.dumps(data)
    
    request = urllib2.Request(options.jiraserver + url,jdata)
    base64string = base64.encodestring('%s:%s' % (options.username, options.password)).replace('\n', '')
    request.add_header("Authorization", "Basic %s" % base64string)   
    request.add_header("Content-Type","application/json")
    request.get_method = lambda: 'PUT'
    
    if options.verbose:
        print "Post: " + options.jiraserver + url
        print "Data: " + jdata

    response = ''
    
    try: 
        response = urllib2.urlopen(request)
    except urllib2.HTTPError, e:
        print('HTTPError = ' + str(e.code) + ' ' + e.read())
        raise(e)

    return json.load(response)
