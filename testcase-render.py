from xml.dom.minidom import Document

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
    
    #logger.info('Report \'' + reportName + '\', ' + str(len(results)) + ' issues')
    #logger.info('%s\t%s\t%s' % ('Key', 'Assignee', 'Summary'))
    for i, v in enumerate(results):
        # For available field names, see the variables in
        # src/java/com/atlassian/jira/rpc/soap/beans/RemoteIssue.java 
        #logger.info('%s\t%s\t%s' % (v['key'], v['assignee'], v['summary']))
        #  print v
        fixVersion = ""
        for version in v['fixVersions']:
            fixVersion += '_' + version['name']
            
            
        testcase = doc.createElement("testcase")
        testcase.setAttribute("classname",reportName)
        testcase.setAttribute("name", v['key'] + fixVersion + "_" + v['assignee'])
        url = "https://jira.jboss.org/browse/" + v['key']
            
        error = doc.createElement("error")
        error.setAttribute("message", desc + "( " + url + " )")

        errortext = doc.createTextNode(v['summary'] + "(" + url + ")" )
        error.appendChild(errortext)
            
        testcase.appendChild(error)
        testsuite.appendChild(testcase)
        
    print doc.toprettyxml(indent="  ")
    return 0    
