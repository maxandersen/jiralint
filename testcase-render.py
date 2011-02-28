from xml.dom.minidom import Document
import datetime
from datetime import timedelta
import pprint

def xstr(s):
    if s is None:
        return 'None'
    else:
        return str(s)
    
def render(self, logger, jira_env, args, results):
    
    if jira_env.has_key('reportName'):
        reportName = jira_env['reportName']
    else:
        reportName = str(jira_env['reportNumber'])
        
    if jira_env.has_key('reportDescription'):
        desc = jira_env['reportDescription']
    else:
        desc = "Unknown"
        
    doc = Document()
    testsuite = doc.createElement("testsuite")
    doc.appendChild(testsuite)

    if len(results) > 0:
        for i, v in enumerate(results):
            # For available field names, see the variables in
            # src/java/com/atlassian/jira/rpc/soap/beans/RemoteIssue.java 
            #logger.info('%s\t%s\t%s' % (v['key'], v['assignee'], v['summary']))
            #  print v
            fixVersion = ""
            for version in v['fixVersions']:
                fixVersion += '_' + version['name']

            testcase = doc.createElement("testcase")
            testcase.setAttribute("classname", reportName)
            testcase.setAttribute("name", reportName + "." + v['key'] + xstr(fixVersion) + "_" + xstr(v['assignee']))
            url = jira_env['server_url'] + '/browse/' + v['key']

       
            error = doc.createElement("error")

            
            lastupdate = datetime.datetime.now() - v['updated']
            error.setAttribute("message", url + " (last update: " + str(lastupdate) + ") -> " + desc)

            errortext = doc.createTextNode(v['key'] + ": " + v['summary'] + "(" + url + ")" )
            error.appendChild(errortext)

            testcase.appendChild(error)
            testsuite.appendChild(testcase)
    else:
        testcase = doc.createElement("testcase")
        testcase.setAttribute("classname", reportName)
        testcase.setAttribute("name", "found.noissues")
        testsuite.appendChild(testcase)
    
    print doc.toprettyxml(indent="  ")
    return 0    
