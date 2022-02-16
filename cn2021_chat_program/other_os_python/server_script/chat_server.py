# packages need to be installed
# PyQt5, requests
import subprocess
import sys

def install(package):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
try:
    from PyQt5.QtWidgets import *
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5 import uic
except ModuleNotFoundError:
    install('PyQt5')

import socket

try:
    from requests import get
except ModuleNotFoundError:
    install('requests')

import re
import json
import os

import time
import random

#CONSTANTS
MAX_LISTEN= 10
MAX_BUFFER_LEN= 1024

ACCEPT_TIMEOUT= 0.1
RECV_TIMEOUT=0.2

PORT_DISTANCE_UNIT=5

PORT_NUM_ERROR=2
PORT_IN_USE_ERROR=3
PW_INVALID=4
NAME_DUPLICATED=5
LOGIN_OK=6
CLIENT_STOP=7
CLIENT_RECV_NONE=8
CLIENT_RECV_TIMEOUT=9
CLIENT_SOCKET_BROKEN=10
SELF_STOP=11
FILE_WRITE_FAIL=12
FILE_TRANSFER_COMPLETE=13
FILE_TRANSFER_FAIL=14
SEND_MSG_OK=15

HEADER_LEN=30

##def makeJSONMSG(type_name, content, from_name=''):
##    json_obj= {}
##    json_obj['type']=type_name
##    json_obj['content']=content
##    json_obj['from_name']=from_name
##    return json.dumps(json_obj).encode('utf-8')

def makeJSONMSG(arglist):
    json_obj= {}
    for i in range(0,len(arglist),2):
        json_obj[arglist[i]]=arglist[i+1]
    return json.dumps(json_obj).encode('utf-8')

def makeHeader(content,bytes_num):
    global HEADER_LEN
    header=content+'|'+str(bytes_num)+'|'
    header+='_'*(HEADER_LEN-len(header))
    return header.encode('utf-8')

#MESSAGES
PW_CORRECT_MSG= 'pw_ok'
PW_INCORRECT_MSG= 'pw_wrong'
NAME_OK_MSG= 'name_ok'
NAME_DUPLICATED_MSG= 'name_duplicated'
LOGIN_OK_MSG= 'login_ok'
MSG_END_MSG= 'msg_end'
ILLEGAL_RECONNECTION_MSG='illegal_reconnection'
KEY_INCORRECT_MSG= 'key_wrong'
NAME_UNREGISTERED_MSG= 'name_unregistered'
CANNOT_MAKE_FILE_MSG= 'cannot_make_file'
FILE_TRANSFER_OK_MSG='file_transfer_ok'
FILE_TRANSFER_FAIL_MSG='file_transfer_fail'
FILE_TRANSFER_COMPLETE_MSG='file_transfer_complete'

#HEADER CONTENTS
HEADER_MSG_CONT= 'msg_cont'
HEADER_MSG_END='msg_end'
HEADER_CLIENT_END='client_end'
HEADER_ALIVE_CHECK='alive_check'
HEADER_SERVER_END='server_end'
HEADER_CONNECTION_CHECK='connection_check'
HEADER_USER_STATUS='user_status'


##SERVER_STATE_STARTED=0
##SERVER_STATE_STOPPED=1

#class for managing all file transfer client worker threads
class fileClientList:
    def __init__(self):
        self.file_client_workers=[]
        self.id_count=0
        #mutex lock
        self.file_client_list_mutex=QReadWriteLock()

    def appendEntry(self,thread,server_thread_id,user_name):
        self.file_client_list_mutex.lockForWrite()
        self.file_client_workers.append({'server_thread_id':server_thread_id,'user_name':user_name,'thread':thread})
        self.file_client_list_mutex.unlock()

    def removeEntry(self,thread):
        global list_changed
        self.file_client_list_mutex.lockForWrite()
        for i in range(len(self.file_client_workers)):
            entry=self.file_client_workers[i]
            if entry['thread'] is thread:
                self.file_client_workers.pop(i)
                break
        self.file_client_list_mutex.unlock()
        list_changed[0]=True

    def setThreadIdAndName(self,target_thread,server_thread_id,user_name):
        self.file_client_list_mutex.lockForWrite()
        for entry in self.file_client_workers:
            if entry['thread']==target_thread:
                entry['server_thread_id']=server_thread_id
                entry['user_name']=user_name
                break
        self.file_client_list_mutex.unlock()

    def signalAllClientByServerThreadID(self,server_thread_id):
        self.file_client_list_mutex.lockForRead()
        for entry in self.file_client_workers:
            if entry['server_thread_id']==server_thread_id:
                entry['thread'].stop()
        self.file_client_list_mutex.unlock()

    def signalAllClientWorkers(self):
        self.file_client_list_mutex.lockForWrite()
        
        for i in range(len(self.file_client_workers)-1,-1,-1):
            entry=self.file_client_workers[i]
            entry.stop()
            self.file_client_workers.pop(-1)

        del self.file_client_workers
        self.file_client_workers=[]
        self.file_client_list_mutex.unlock()

    def getListLen(self):
        return len(self.file_client_workers)

#class for managing all client worker threads
class clientList:
    def __init__(self):
        self.client_workers=[]
        self.id_count=0
        #mutex lock
        self.client_list_mutex=QReadWriteLock()


    def checkNameDuplicatedAndRegister(self,conn_socket,name,thread):
        self.client_list_mutex.lockForWrite()
        duplicated= False
        for entry in self.client_workers:
            if entry['name']==name:
                duplicated=True
                break
        if not duplicated:
            self.id_count+=1
            new_entry= self.makeNewEntry(conn_socket,name,thread)
            self.client_workers.append(new_entry)
            thread.setThreadID(self.id_count)
            thread.setReconnectionCount(0)
        self.client_list_mutex.unlock()
        return duplicated

    def checkNameRegisteredAndUpdate(self,conn_socket,name,thread):
        self.client_list_mutex.lockForWrite()
        registered= False
        for entry in self.client_workers:
            if entry['name']==name:
                registered=True
                entry['conn_socket']=conn_socket
                entry['thread']=thread
                thread.setThreadID(entry['id'])
                thread.setReconnectionCount(entry['reconnection_count']+1)
                break
        self.client_list_mutex.unlock()
        return registered

    def checkNameRegistered(self,name):
        thread_id=None
        registered= False
        self.client_list_mutex.lockForWrite()
        for entry in self.client_workers:
            if entry['name']==name:
                registered=True
                thread_id=entry['id']
                break
        self.client_list_mutex.unlock()
        return (registered,thread_id)

    def makeNewEntry(self,conn_socket,name,thread):
        return {'id':self.id_count,'conn_socket':conn_socket,'name':name,'thread':thread,\
                'reconnection_count':0, 'connected':True}

    def removeEntry(self,thread):
        global list_changed
        self.client_list_mutex.lockForWrite()
        for i in range(len(self.client_workers)):
            entry=self.client_workers[i]
            if entry['id']==thread.thread_id:
                self.client_workers.pop(i)
                break
        self.client_list_mutex.unlock()
        list_changed[0]=True

    def updateUserStatusIfValid(self, thread_id, connected, reconnection_count):
        valid=True
        self.client_list_mutex.lockForWrite()
        for entry in self.client_workers:
            if entry['id']==thread_id:
                if (connected==True and reconnection_count<=entry['reconnection_count']) or \
                   (connected==False and reconnection_count<entry['reconnection_count']):
                    valid=False
                    break
                entry['connected']=connected
                entry['reconnection_count']=reconnection_count
        self.client_list_mutex.unlock()
        return valid

    def getUserStatusList(self,thread_id):
        user_status_list=[]
        self.client_list_mutex.lockForRead()
        for entry in self.client_workers:
            if entry['id']!=thread_id:
                user_status_list.append((entry['name'],entry['connected']))
        self.client_list_mutex.unlock()
        return user_status_list

    def signalAllClientWorkers(self):
        self.client_list_mutex.lockForWrite()
        
        for i in range(len(self.client_workers)-1,-1,-1):
            entry=self.client_workers[i]
            entry['thread'].stop()
            self.client_workers.pop(-1)

        del self.client_workers
        self.client_workers=[]
        self.client_list_mutex.unlock()

    def broadcastMSG(self, msg_data):
        self.client_list_mutex.lockForRead()
        for entry in self.client_workers:
            if entry['id']==msg_data['thread_from']:
                continue
            entry['thread'].appendBroadcastMSG(msg_data)
        self.client_list_mutex.unlock()

    def broadcastUserStatus(self, user_status_data):
        valid=True
        if user_status_data['option']=='change':
            valid=self.updateUserStatusIfValid(user_status_data['thread_from'],user_status_data['connected'],\
                                               user_status_data['reconnection_count'])
        if not valid:
            return
        self.client_list_mutex.lockForWrite()
        for entry in self.client_workers:
            if entry['id']==user_status_data['thread_from']:
                continue
            entry['thread'].appendBroadcastMSG(user_status_data)
        self.client_list_mutex.unlock()

    def getListLen(self):
        return len(self.client_workers)

#mutex lock
keep_running_mutex=QMutex()
##client_workers_mutex=QMutex()

#global variables
keep_running=[True]
##client_workers=[]
client_list=clientList()
file_client_list=fileClientList()

list_changed=[False]
##client_candidate_list=[]

dialog_form_class = uic.loadUiType("dialog.ui")[0]
server_form_class = uic.loadUiType("serverPrompt.ui")[0]

password_regex= re.compile('[a-zA-Z0-9!@#%&*]+')
name_regex= re.compile('[a-zA-Z0-9_]+')

##class AltEnterSignal(QObject):

class threadCollectWorker(QThread):
    def __init__(self,parent):
        global keep_running
        super().__init__()
        self.parent=parent
        self.keep_running=keep_running

        #collected thread list
        self.thread_list=[]
        self.thread_list_mutex=QMutex()

    def run(self):
        global client_list, file_client_list
        global list_changed
        while self.keep_running[0]:
            time.sleep(0.1)
            if len(self.thread_list)<=0:
                continue
            self.thread_list_mutex.lock()
            current_thread=self.thread_list.pop(0)
            self.thread_list_mutex.unlock()
            current_thread.stop()
            current_thread.wait()

        while len(self.thread_list)>0 or \
              client_list.getListLen()>0 or \
              file_client_list.getListLen()>0 or \
              list_changed[0]:
            if len(self.thread_list)>0:
                self.thread_list_mutex.lock()
                current_thread=self.thread_list.pop(0)
                current_thread.stop()
                current_thread.wait()
                self.thread_list_mutex.unlock()
            else:
                time.sleep(0.1)
            list_changed[0]=False

        print(f'len1: {len(self.thread_list)}, len2: {client_list.getListLen()}, len3: {file_client_list.getListLen()}')

    def appendThread(self,thread):
        self.thread_list_mutex.lock()
        self.thread_list.append(thread)
        self.thread_list_mutex.unlock()

    def stop(self):
        self.keep_running[0]=False

class msgBroadcastWorker(QThread):
    def __init__(self,parent):
        global keep_running, client_list
        super().__init__()
        self.parent=parent
        self.client_list= client_list
        self.keep_running=keep_running

        #global broadcast messages list(list for all clients)
        self.global_broadcast_msg_list=[]
        self.list_mutex=QMutex()

        #global broadcast user status data list(list for all clients)
        self.global_broadcast_user_status_data_list=[]
        self.status_list_mutex=QMutex()

    def run(self):
        while keep_running[0]:
            idle=True
            
            if len(self.global_broadcast_msg_list)>0:
                idle=False
                self.list_mutex.lock()
                msg_data=self.global_broadcast_msg_list.pop(0)
                self.list_mutex.unlock()
                self.client_list.broadcastMSG(msg_data)

            if len(self.global_broadcast_user_status_data_list)>0:
                idle=False
                self.status_list_mutex.lock()
                user_status_data=self.global_broadcast_user_status_data_list.pop(0)
                self.status_list_mutex.unlock()
                self.client_list.broadcastUserStatus(user_status_data)

            if idle:
                time.sleep(0.1)
                
                         

    def appendMSGData(self,msg_data):
        self.list_mutex.lock()
        self.global_broadcast_msg_list.append(msg_data)
        self.list_mutex.unlock()

    def appendUserStatusData(self,user_status_data):
        self.status_list_mutex.lock()
        self.global_broadcast_user_status_data_list.append(user_status_data)
        self.status_list_mutex.unlock()

    def stop(self):
        self.keep_running[0]=False

class fileMapList():
    def __init__(self):
        self.map_list=[]
        self.map_list_mutex=QReadWriteLock()
        self.file_id=0
        self.file_id_mutex=QMutex()
    def getFileIDAndRealName(self,file_name,user_name):
        #get file id
        self.file_id_mutex.lock()
        return_id=self.file_id
        self.file_id+=1
        self.file_id_mutex.unlock()

        #insert entry to list
        _,ext=os.path.splitext(file_name)
        real_file_name=time.strftime('%Y%m%d%H%M%S',time.gmtime())+'_'+user_name+ext
        entry={'id':return_id,'file_name':file_name,'real_file_name':real_file_name,\
               'user_name':user_name}
        self.map_list_mutex.lockForWrite()
        self.map_list.append(entry)
        self.map_list_mutex.unlock()
        
        return (return_id,real_file_name)
    def getRealFileNameByID(self,target_id):
        real_file_name=None
        self.map_list_mutex.lockForRead()
        for entry in self.map_list:
            if entry['id']==target_id:
                real_file_name=entry['real_file_name']
                break
        self.map_list_mutex.unlock()
        return real_file_name

class fileClientWorker(QThread):
    resultSignal= pyqtSignal(dict)
    def __init__(self,parent,conn_socket,ip_addr,msg_broadcast_thread,client_thread_collector_thread,\
                 file_transfer_key, base_file_path):
        global keep_running
        super().__init__()
        self.parent=parent
        self.conn_socket=conn_socket
        self.ip_addr=ip_addr
        self.keep_running=keep_running
        self.thread_stop=False

        self.user_name= None
        self.server_thread_id=None
        self.file_name=None
        self.file_id=None
        self.real_file_name=None
        self.file= None
        

        #pointer of thread for message broadcasting
        self.msg_broadcast_thread=msg_broadcast_thread

        #pointer of thread for thread collecting
        self.client_thread_collector_thread= client_thread_collector_thread

        #key for transferring file
        self.file_transfer_key=file_transfer_key

        #variables for pre-read header
        self.header_reserved=None
        self.bytes_num_follow=None

        #base file path
        self.base_file_path=base_file_path
        self.dir_name= 'server_repos'

        #progress rate calculation
        self.file_size=None

    def run(self):
        global PW_CORRECT_MSG, PW_INCORRECT_MSG
        global NAME_OK_MSG, NAME_DUPLICATED_MSG
        global LOGIN_OK_MSG, ILLEGAL_RECONNECTION_MSG
        global KEY_INCORRECT_MSG, NAME_UNREGISTERED_MSG
        global CANNOT_MAKE_FILE_MSG, FILE_TRANSFER_OK_MSG
        global HEADER_MSG_CONT, HEADER_MSG_END
        global HEADER_CLIENT_END, HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global CLIENT_STOP, CLIENT_RECV_NONE
        global CLIENT_RECV_TIMEOUT, CLIENT_SOCKET_BROKEN
        global SELF_STOP, FILE_WRITE_FAIL
        global SEND_MSG_OK
        global FILE_TRANSFER_COMPLETE, FILE_TRANSFER_FAIL
        global file_client_list, name_regex

        #check key and name registered
        login_info_json=self.recvMsgFromClient(3)
        if login_info_json== CLIENT_RECV_NONE or \
           login_info_json== CLIENT_SOCKET_BROKEN:
            self.closeAllSocket()
            self.safeRemoveThisWorker()
            self.resultSignal.emit({'validation_success':False, 'thread':self})
            return
        #key check
        if login_info_json['file_transfer_key']!=self.file_transfer_key:
            print('key wrong')
            try:
##                self.conn_socket.send(makeJSONMSG(['type','login','content',KEY_INCORRECT_MSG]))
                self.sendMsgToClient(makeJSONMSG(['type','login','content',KEY_INCORRECT_MSG]))
            except socket.error:
                pass
            self.closeAllSocket()
            self.safeRemoveThisWorker()
            self.resultSignal.emit({'validation_success':False, 'thread':self})
            return
        #name check
        self.user_name= login_info_json['user_name']
        self.server_thread_id=login_info_json['server_thread_id']
        name_registered,thread_id= client_list.checkNameRegistered(self.user_name)
        self.server_thread_id=thread_id
        if not name_registered:
            print('name not registered')
            try:
##                self.conn_socket.send(makeJSONMSG(['type','login','content',NAME_UNREGISTERED_MSG]))
                self.sendMsgToClient(makeJSONMSG(['type','login','content',NAME_UNREGISTERED_MSG]))
            except socket.error:
                pass
            self.closeAllSocket()
            self.safeRemoveThisWorker()
            self.resultSignal.emit({'validation_success':False, 'thread':self})
            return
        file_upload=login_info_json['subtype']=='upload'
        if file_upload:
            #try to mkdir and open file
            #mk dir
            target_file_path=None
            if self.base_file_path.find('/')>=0:
                target_file_path='/'.join((self.base_file_path,self.dir_name))
            else:
                target_file_path=os.path.join(self.base_file_path,self.dir_name)
            mkdir_success=True
            if not os.path.isdir(self.dir_name):
                try:
                    os.mkdir(self.dir_name)
                except Exception as e:
                    print(e)
                    mkdir_success=False
            if not mkdir_success:
                print('cannot mkdir')
                try:
##                    self.conn_socket.send(makeJSONMSG(['type','login','content',CANNOT_MAKE_FILE_MSG]))
                    self.sendMsgToClient(makeJSONMSG(['type','login','content',CANNOT_MAKE_FILE_MSG]))
                except socket.error:
                    pass
                self.closeAllSocket()
                self.safeRemoveThisWorker()
                self.resultSignal.emit({'validation_success':False, 'thread':self})
                return
            #make file
            self.file_name= login_info_json['file_name']
            file_open_success=True
            file=None
            file_id,real_file_name= self.parent.getFileIDAndRealName(self.file_name,self.user_name)
            self.file_id=file_id
            self.real_file_name=real_file_name
            file_path_real_name=os.path.join(self.dir_name,real_file_name)
            try:
                file=open(file_path_real_name,'wb')
                self.file=file
            except Exception as e:
                print(e)
                file_open_success=False
            if not file_open_success:
                print('file open fail')
                try:
##                    self.conn_socket.send(makeJSONMSG(['type','login','content',CANNOT_MAKE_FILE_MSG]))
                    self.sendMsgToClient(makeJSONMSG(['type','login','content',CANNOT_MAKE_FILE_MSG]))
                except socket.error:
                    pass
                self.closeAllSocket()
                self.safeRemoveThisWorker()
                self.resultSignal.emit({'validation_success':False, 'thread':self})
                return
        else:
            #try to open file
            self.file_name= login_info_json['file_name']
            self.file_id= login_info_json['file_id']
            self.real_file_name= self.parent.getRealFileNameByID(self.file_id)
            file_open_success=True
            file=None
            file_path_real_name=os.path.join(self.dir_name,self.real_file_name)
            try:
                file=open(file_path_real_name,'rb')
                self.file=file
                self.file_size=os.path.getsize(file_path_real_name)
            except Exception as e:
                print(e)
                file_open_success=False
            if not file_open_success:
                print('file open fail')
                try:
##                    self.conn_socket.send(makeJSONMSG(['type','login','content',CANNOT_MAKE_FILE_MSG]))
                    self.sendMsgToClient(makeJSONMSG(['type','login','content',CANNOT_MAKE_FILE_MSG]))
                except socket.error:
                    pass
                self.closeAllSocket()
                self.safeRemoveThisWorker()
                self.resultSignal.emit({'validation_success':False, 'thread':self})
                return
        #send ok msg to client
##        try:
##            if file_upload:
##                self.conn_socket.send(makeJSONMSG(['type','login','content',FILE_TRANSFER_OK_MSG]))
##            else:
##                self.conn_socket.send(makeJSONMSG(['type','login','content',FILE_TRANSFER_OK_MSG, \
##                                                   'file_size',self.file_size]))
##        except socket.error:
##            self.closeAllSocket()
##            self.closeFile()
##            if file_upload:
##                self.deleteFile()
##            self.safeRemoveThisWorker()
##            self.resultSignal.emit({'validation_success':False, 'thread':self})
##            return
        return_val=None
        if file_upload:
            return_val=self.sendMsgToClient(makeJSONMSG(['type','login','content',FILE_TRANSFER_OK_MSG]))
        else:
            return_val=self.sendMsgToClient(makeJSONMSG(['type','login','content',FILE_TRANSFER_OK_MSG, \
                                               'file_size',self.file_size]))
        if return_val != SEND_MSG_OK:
            self.closeAllSocket()
            self.closeFile()
            if file_upload:
                self.deleteFile()
            self.safeRemoveThisWorker()
            self.resultSignal.emit({'validation_success':False, 'thread':self})
            return

        file_client_list.appendEntry(self,self.server_thread_id,self.user_name)
        self.resultSignal.emit({'validation_success':True, 'thread':self})

        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            self.parent.collectorAppend(self)
            self.removeThisWorker()
            return
            
        
        #after open file, the file user name, file name, real file name should be conveyed to main window

        if file_upload:
            #recv file byte stream
            return_val=self.recvFileFromClient(3)
            print('after recv file')
            if return_val==FILE_TRANSFER_COMPLETE:
                #do something here
                pass
            elif return_val==SELF_STOP:
                print('last self stop')
                self.closeAllSocket()
                self.closeFile()
                self.deleteFile()
                self.parent.collectorAppend(self)
                self.removeThisWorker()
                return
            else:
                print(f'last, return_val: {return_val}')
                self.closeAllSocket()
                self.closeFile()
                self.deleteFile()
                self.parent.collectorAppend(self)
                self.removeThisWorker()
                return

            #send msg to broadcast file
            self.msg_broadcast_thread.appendMSGData({'type':'broadcast_file','thread_from':self.server_thread_id,\
                                                     'name':self.user_name,'msg':self.file_name,\
                                                     'file_name':self.file_name, 'file_id':self.file_id})
        else:
            #send file bytestream
            return_val=self.sendFileToClient(self.file)
            print('after send file')
            if return_val==FILE_TRANSFER_COMPLETE:
                #do something here
                pass
            elif return_val==SELF_STOP:
                print('last self stop')
                self.closeAllSocket()
                self.closeFile()
                self.parent.collectorAppend(self)
                self.removeThisWorker()
                return
            else:
                print(f'last, return_val: {return_val}')
                self.closeAllSocket()
                self.closeFile()
                self.parent.collectorAppend(self)
                self.removeThisWorker()
                return
        #above should be done to broadcast file
        self.closeAllSocket()
        self.closeFile()
        self.parent.collectorAppend(self)
        self.removeThisWorker()
        

    def sendFileToClient(self,file):
        global MAX_BUFFER_LEN, HEADER_LEN
        global SOCKET_BROKEN, CLIENT_STOP
        global SELF_STOP, SEND_MSG_OK
        global FILE_TRANSFER_FAIL, FILE_TRANSFER_COMPLETE
        global FILE_TRANSFER_FAIL_MSG, FILE_TRANSFER_COMPLETE_MSG
        global HEADER_CLIENT_END

        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            return SELF_STOP

        #second send file byte stream
        prev_timeout=self.conn_socket.gettimeout()
        self.conn_socket.settimeout(5)
        try:
            while self.keep_running[0] and not self.thread_stop:
                #send file byte stream
                file_data=file.read(MAX_BUFFER_LEN-HEADER_LEN)
                header=None
                if not file_data:
                    header= makeHeader(HEADER_MSG_END,len(file_data))
                else:
                    header= makeHeader(HEADER_MSG_CONT,len(file_data))
                self.conn_socket.send(header + file_data)
                if not file_data:
                    break

            #check if this thread should stop
            if self.checkStopAndClose()==SELF_STOP:
                return SELF_STOP

            #receive msg that the file has transferred successfully
            
##            reply_json= json.loads(self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8'))
            
        except socket.timeout as e:
            print(e)
            print('recv reply timeout')
            return SOCKET_BROKEN
        except socket.error as e:
            print(e)
            return SOCKET_BROKEN
        except Exception as e:
            print(e)
            return FILE_TRANSFER_FAIL

        reply_json=self.recvMsgFromClient(5)
        
        self.conn_socket.settimeout(prev_timeout)

        if type(reply_json) is not dict:
            return SOCKET_BROKEN

        if reply_json['content']==FILE_TRANSFER_COMPLETE_MSG:
            return FILE_TRANSFER_COMPLETE
        else:
            return FILE_TRANSFER_FAIL

    def recvFileFromClient(self,timeout):
        global HEADER_MSG_CONT, HEADER_MSG_END
        global HEADER_CLIENT_END, HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global CLIENT_STOP, CLIENT_RECV_NONE
        global CLIENT_RECV_TIMEOUT, CLIENT_SOCKET_BROKEN
        global SELF_STOP, FILE_WRITE_FAIL
        global SEND_MSG_OK
        global FILE_TRANSFER_COMPLETE
        global FILE_TRANSFER_FAIL_MSG, FILE_TRANSFER_COMPLETE_MSG
        #first receive broadcast message bytestream from client
##        broadcast_msg=b''
        tmp_bytestream=b''
        prev_timeout=self.conn_socket.gettimeout()
        self.conn_socket.settimeout(timeout) # maximum 'first_timeout' seconds waiting
        header_content, bytes_num_follow=None,None
        try:
            #receive header stream
            tmp_msg=b''
            while len(tmp_msg)<HEADER_LEN:
                tmp_msg+= self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
            tmp_msg= tmp_msg.decode('utf-8')
        except socket.timeout:
            return CLIENT_RECV_NONE
        except socket.error as e:
            return CLIENT_SOCKET_BROKEN
        except Exception as e:
            print(e)
            print(f'tmp_msg: {tmp_msg}')
            try:
                self.sendMsgToClient(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_FAIL_MSG]))
            except:
                pass
            return FILE_WRITE_FAIL
        
        header_content, bytes_num_follow, _=tmp_msg.split('|')
##        print(f'tmp_msg: {tmp_msg}')
        bytes_num_follow=int(bytes_num_follow)
        
        get_next_msg=False
        if header_content==HEADER_MSG_CONT:
            get_next_msg=True

            
##        self.conn_socket.settimeout(2) # maximum 2 seconds waiting
        
        try:
            tmp_bytestream=b''
            while len(tmp_bytestream)<bytes_num_follow:
                tmp_bytestream+=self.conn_socket.recv(bytes_num_follow-len(tmp_bytestream))
            if len(tmp_bytestream)!=bytes_num_follow:
                print(f'tmp_bytestream len: {len(tmp_bytestream)}, bytes_num_follow: {bytes_num_follow}')
            self.file.write(tmp_bytestream)
        except socket.timeout:
            return CLIENT_SOCKET_BROKEN
        except socket.error as e:
            return CLIENT_SOCKET_BROKEN
        except Exception as e:
            print(e)
            print('cannot write to file')
            try:
                self.sendMsgToClient(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_FAIL_MSG]))
            except:
                pass
            return FILE_WRITE_FAIL

        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            return SELF_STOP
        print('after first check thread stop')
        
        #receive continuing stream if exists
        print(f'get next msg: {get_next_msg}')
        while get_next_msg:
##            print('inside file recv loop')
            #check if this thread should stop
            if self.checkStopAndClose()==SELF_STOP:
                return SELF_STOP
            
            try:
                tmp_msg=b''
                while len(tmp_msg)<HEADER_LEN:
                    tmp_msg+= self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
                tmp_msg= tmp_msg.decode('utf-8')
            except socket.timeout:
                return CLIENT_SOCKET_BROKEN
            except socket.error as e:
                return CLIENT_SOCKET_BROKEN
            except Exception as e:
                print(e)
                print(f'tmp_msg: {tmp_msg}')
                try:
                    self.sendMsgToClient(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_FAIL_MSG]))
                except:
                    pass
                return FILE_WRITE_FAIL
##            print(f'inside loop, tmp_msg: {tmp_msg}')
            
##            try:
##                header_content, bytes_num_follow, _=tmp_msg.split('|')
##            except Exception as e:
##                print(e)
##                print(f'last tmp_msg: {tmp_msg}')
            
            header_content, bytes_num_follow, _=tmp_msg.split('|')
            bytes_num_follow=int(bytes_num_follow)
            if header_content==HEADER_MSG_END:
                get_next_msg=False
                break

            try:
                tmp_bytestream=b''
                while len(tmp_bytestream)<bytes_num_follow:
                    tmp_bytestream+=self.conn_socket.recv(bytes_num_follow-len(tmp_bytestream))
                if len(tmp_bytestream)!=bytes_num_follow:
                    print(f'tmp_bytestream len: {len(tmp_bytestream)}, bytes_num_follow: {bytes_num_follow}')
                self.file.write(tmp_bytestream)
            except socket.timeout:
                return CLIENT_SOCKET_BROKEN
            except socket.error as e:
                return CLIENT_SOCKET_BROKEN
            except Exception as e:
                print(e)
                try:
                    self.sendMsgToClient(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_FAIL_MSG]))
                except:
                    pass
                return FILE_WRITE_FAIL
                
##        try:
##            self.conn_socket.send(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_COMPLETE_MSG]))
##        except Exception as e:
##            return CLIENT_SOCKET_BROKEN
        return_val= self.sendMsgToClient(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_COMPLETE_MSG]))
        if return_val != SEND_MSG_OK:
            return CLIENT_SOCKET_BROKEN
        self.conn_socket.settimeout(prev_timeout) # prev timeout restore
        return FILE_TRANSFER_COMPLETE


    def recvMsgFromClient(self,first_timeout):
        global HEADER_MSG_CONT, HEADER_MSG_END
        global HEADER_CLIENT_END, HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global CLIENT_STOP, CLIENT_RECV_NONE
        global CLIENT_RECV_TIMEOUT, CLIENT_SOCKET_BROKEN
        #first receive broadcast message bytestream from client
        broadcast_msg=''
        tmp_msg=''
        prev_timeout=self.conn_socket.gettimeout()
        self.conn_socket.settimeout(first_timeout) # maximum 'first_timeout' seconds waiting
        header_content, bytes_num_follow=None,None
        try:
            #receive header stream
            tmp_msg=b''
            while len(tmp_msg)<HEADER_LEN:
                tmp_msg+= self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
            tmp_msg= tmp_msg.decode('utf-8')
        except socket.timeout:
            return CLIENT_RECV_NONE
        except socket.error as e:
            #connection rebuilding goes here
            return CLIENT_SOCKET_BROKEN
        
        header_content, bytes_num_follow, _=tmp_msg.split('|')
        bytes_num_follow=int(bytes_num_follow)
        
        get_next_msg=False
        if header_content==HEADER_MSG_CONT:
            get_next_msg=True

            
##        self.conn_socket.settimeout(2) # maximum 2 seconds waiting
        
        try:
            tmp_bytestream=b''
            while len(tmp_bytestream)<bytes_num_follow:
                tmp_bytestream+=self.conn_socket.recv(bytes_num_follow-len(tmp_bytestream))
            broadcast_msg+=tmp_bytestream.decode('utf-8')
        except socket.timeout:
            #connection rebuilding goes here
            return CLIENT_SOCKET_BROKEN
        except socket.error as e:
            #connection rebuilding goes here
            return CLIENT_SOCKET_BROKEN
        
        #receive continuing stream if exists
        while get_next_msg:
            tmp_msg=''
            try:
                tmp_msg=b''
                while len(tmp_msg)<HEADER_LEN:
                    tmp_msg+= self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
                tmp_msg= tmp_msg.decode('utf-8')
            except socket.timeout:
                #connection rebuilding goes here
                return CLIENT_SOCKET_BROKEN
            except socket.error as e:
                #connection rebuilding goes here
                return CLIENT_SOCKET_BROKEN
            header_content, bytes_num_follow, _=tmp_msg.split('|')
            bytes_num_follow=int(bytes_num_follow)
            if header_content==HEADER_MSG_END:
                get_next_msg=False

            try:
                tmp_bytestream=b''
                while len(tmp_bytestream)<bytes_num_follow:
                    tmp_bytestream+=self.conn_socket.recv(bytes_num_follow-len(tmp_bytestream))
                broadcast_msg+=tmp_bytestream.decode('utf-8')
            except socket.timeout:
                #connection rebuilding goes here
                return CLIENT_SOCKET_BROKEN
            except socket.error as e:
                #connection rebuilding goes here
                return CLIENT_SOCKET_BROKEN
                
        self.conn_socket.settimeout(prev_timeout) # prev timeout restore

        #second try to convert received msg to json obj
        broadcast_msg_json={}
        try:
            broadcast_msg_json= json.loads(broadcast_msg)
        except json.JSONDecodeError:
            #just discard received broadcasted bytestream
            return CLIENT_RECV_NONE
        return broadcast_msg_json

    def sendMsgToClient(self,msg_byte_stream):
        global MAX_BUFFER_LEN, HEADER_LEN
        global SOCKET_BROKEN
        global SEND_MSG_OK
        global HEADER_MSG_CONT, HEADER_MSG_END
        byte_stream_index=0
        byte_stream_len= len(msg_byte_stream)
        prev_timeout=self.conn_socket.gettimeout()
        self.conn_socket.settimeout(5) # maximum 5 seconds waiting to check password
        try:
            while byte_stream_index<byte_stream_len:
                if byte_stream_len-byte_stream_index>MAX_BUFFER_LEN-HEADER_LEN:
                    self.conn_socket.send(makeHeader(HEADER_MSG_CONT,MAX_BUFFER_LEN-HEADER_LEN) + \
                        msg_byte_stream[byte_stream_index:byte_stream_index+(MAX_BUFFER_LEN-HEADER_LEN)])
                else:
                    self.conn_socket.send(makeHeader(HEADER_MSG_END,byte_stream_len-byte_stream_index) + \
                        msg_byte_stream[byte_stream_index:byte_stream_len])
                byte_stream_index+=MAX_BUFFER_LEN-HEADER_LEN
        except socket.timeout:
            return SOCKET_BROKEN
        except socket.error:
            return SOCKET_BROKEN
        
        self.conn_socket.settimeout(prev_timeout) # restore timeout

        return SEND_MSG_OK

    def stop(self):
        self.thread_stop=True
        
    def closeAllSocket(self):
        try:
            self.conn_socket.close()
        except:
            pass

    def closeFile(self):
        if self.file is not None:
            try:
                self.file.close()
            except:
                pass

    def deleteFile(self):
        if self.real_file_name is not None and os.path.isfile(self.real_file_name):
            try:
                os.remove(self.real_file_name)
            except:
                pass

    def checkStopAndClose(self):
        global SELF_STOP
        if not self.keep_running[0] or self.thread_stop:
            self.closeFile()
            self.deleteFile()
            self.closeAllSocket()
            return SELF_STOP
        return False

    def safeRemoveThisWorker(self):
        global file_client_list
        self.client_thread_collector_thread.appendThread(self)
        file_client_list.removeEntry(self)

    def removeThisWorker(self):
        global file_client_list
        if self.file_id is None:
            return
        file_client_list.removeEntry(self)

class clientWorker(QThread):
    userEntrySignal= pyqtSignal(dict)
    confirmSignal= pyqtSignal(dict)
    def __init__(self,parent,conn_socket,ip_addr,pw,msg_broadcast_thread,\
                 file_server_port,file_transfer_key):
        global keep_running
        super().__init__()
        self.parent=parent
        self.conn_socket=conn_socket
        self.ip_addr=ip_addr
        self.pw=pw
        self.keep_running=keep_running
        self.thread_stop=False

        self.user_name= None
        self.thread_id=None

        #pointer of thread for message broadcasting
        self.msg_broadcast_thread=msg_broadcast_thread

        #list for broadcast other clients' messages
        self.broadcast_msg_list=[]
        self.broadcast_msg_list_mutex= QMutex()

        #variables for pre-read header
        self.header_reserved=None
        self.bytes_num_follow=None

        #reconnection count of this thread(total count)
        self.reconnection_count=None

        #key and port for file tansfer
        self.file_server_port=file_server_port
        self.file_transfer_key=file_transfer_key


    def run(self):
        global PW_CORRECT_MSG, PW_INCORRECT_MSG
        global NAME_OK_MSG, NAME_DUPLICATED_MSG
        global LOGIN_OK_MSG, ILLEGAL_RECONNECTION_MSG
        global HEADER_MSG_CONT, HEADER_MSG_END
        global HEADER_CLIENT_END, HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global CLIENT_STOP, CLIENT_RECV_NONE
        global CLIENT_RECV_TIMEOUT, CLIENT_SOCKET_BROKEN
        global SEND_MSG_OK
        global client_list, name_regex
        
##        #first check password is correct, if not, then terminate thread
##        password_ok=True
##        self.conn_socket.settimeout(3) # maximum 3 seconds waiting to check password
##        try:
##            msg_json= json.loads(self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8'))
##            if msg_json['content'] != self.pw:
##                self.conn_socket.send(makeJSONMSG(['type','login','content',PW_INCORRECT_MSG]))
##                self.closeAllSocket() # close client socket
##                return
##            self.conn_socket.send(makeJSONMSG(['type','login','content',PW_CORRECT_MSG]))
##        except socket.timeout as e:
##            self.closeAllSocket()
##            return
##        except socket.error as e:
##            self.closeAllSocket()
##            print(f'socket.error occurred, first block :{e}')
##            return
##        
##
##        self.conn_socket.settimeout(None) # turn connection socket to blocking mode
##        
##        #check if name is already registered and register client if possible
##        self.conn_socket.settimeout(3) # maximum 3 seconds waiting to check name
##        try:
##            msg_json=json.loads(self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8'))
##            #check if name is valid
##            if not name_regex.match(msg_json['content']):
##                self.conn_socket.send(makeJSONMSG(['type','login','content',NAME_DUPLICATED_MSG]))
##                self.closeAllSocket()
##                return
##            #check if name is duplicated
##            name_duplicated= client_list.checkNameDuplicatedAndRegister(self.conn_socket,msg_json['content'],self)
##            if not name_duplicated:
##                self.conn_socket.send(makeJSONMSG(['type','login','content',NAME_OK_MSG]))
##                self.user_name=msg_json['content']
##            else:
##                self.conn_socket.send(makeJSONMSG(['type','login','content',NAME_DUPLICATED_MSG]))
##                self.closeAllSocket()
##                return
##        except socket.error as e:
##            #close socket and remove this worker from global client worker thread list
##            self.closeAllSocket()
##            self.removeThisWorker()
##            return
##        self.conn_socket.settimeout(None) # turn connection socket to blocking mode

        #check password and name and register client if possible + reconnection handling
        re_connection= False
        login_info_json=self.recvMsgFromClient(3)
        if login_info_json==CLIENT_RECV_NONE or\
           login_info_json==CLIENT_SOCKET_BROKEN:
            #the case where socket is broken
            self.closeAllSocket()
            self.confirmSignal.emit({'validation_success':False, 'thread':self}) #client thread handling
            return
        self.reconnection_count=login_info_json['reconnection_count']
        re_connection= login_info_json['reconnection_count']>0
        try:
            #check if password is correct
            if login_info_json['pw'] != self.pw:
##                self.conn_socket.send(makeJSONMSG(['type','login','content',PW_INCORRECT_MSG]))
                self.sendMsgToClient(makeJSONMSG(['type','login','content',PW_INCORRECT_MSG]))
                self.closeAllSocket() # close client socket
                self.confirmSignal.emit({'validation_success':False, 'thread':self}) #client thread handling
                return
            if not re_connection:
                #check if name is valid
                if not name_regex.match(login_info_json['name']):
##                    self.conn_socket.send(makeJSONMSG(['type','login','content',NAME_DUPLICATED_MSG]))
                    self.sendMsgToClient(makeJSONMSG(['type','login','content',NAME_DUPLICATED_MSG]))
                    self.closeAllSocket()
                    self.confirmSignal.emit({'validation_success':False, 'thread':self}) #client thread handling
                    return
                #check if name is duplicated
                name_duplicated= client_list.checkNameDuplicatedAndRegister(self.conn_socket,login_info_json['name'],self)
                if not name_duplicated:
##                    self.conn_socket.send(makeJSONMSG(['type','login','content',LOGIN_OK_MSG,\
##                                                       'file_server_port',self.file_server_port,\
##                                                       'file_transfer_key',self.file_transfer_key,\
##                                                       'thread_id',self.thread_id]))
                    return_val= self.sendMsgToClient(makeJSONMSG(['type','login','content',LOGIN_OK_MSG,\
                                                       'file_server_port',self.file_server_port,\
                                                       'file_transfer_key',self.file_transfer_key,\
                                                       'thread_id',self.thread_id]))
                    if return_val != SEND_MSG_OK:
                        self.closeAllSocket()
                        if not re_connection:
                            self.removeThisWorker()
                        self.confirmSignal.emit({'validation_success':False, 'thread':self}) #client thread handling
                        return
                    self.user_name=login_info_json['name']
                else:
##                    self.conn_socket.send(makeJSONMSG(['type','login','content',NAME_DUPLICATED_MSG]))
                    self.sendMsgToClient(makeJSONMSG(['type','login','content',NAME_DUPLICATED_MSG]))
                    self.closeAllSocket()
                    self.confirmSignal.emit({'validation_success':False, 'thread':self}) #client thread handling
                    return
            else:
                #check if received name is registered in client list
                name_registered=client_list.checkNameRegisteredAndUpdate(self.conn_socket,login_info_json['name'],self)
                if name_registered:
                    #send ok msg with file transfer server port and key
##                    self.conn_socket.send(makeJSONMSG(['type','login','content',LOGIN_OK_MSG]))
                    return_val= self.sendMsgToClient(makeJSONMSG(['type','login','content',LOGIN_OK_MSG]))
                    if return_val != SEND_MSG_OK:
                        self.closeAllSocket()
                        if not re_connection:
                            self.removeThisWorker()
                        self.confirmSignal.emit({'validation_success':False, 'thread':self}) #client thread handling
                        return
                    self.user_name=login_info_json['name']
                else:
##                    self.conn_socket.send(makeJSONMSG(['type','login','content',ILLEGAL_RECONNECTION_MSG]))
                    self.sendMsgToClient(makeJSONMSG(['type','login','content',ILLEGAL_RECONNECTION_MSG]))
                    self.closeAllSocket()
                    self.confirmSignal.emit({'validation_success':False, 'thread':self}) #client thread handling
                    return
        except socket.error as e:
            #close socket and remove this worker from global client worker thread list
            self.closeAllSocket()
            if not re_connection:
                self.removeThisWorker()
            self.confirmSignal.emit({'validation_success':False, 'thread':self}) #client thread handling
            return
        
        self.conn_socket.settimeout(None) # turn connection socket to blocking mode

        self.confirmSignal.emit({'validation_success':True, 'thread':self}) #client thread handling


        if not re_connection:
            #send signal to main window to register new user's name
            self.userEntrySignal.emit({'in':True,'out':False,'name':self.user_name,'thread':self})
            #broadcast this client user is entered
            self.msg_broadcast_thread.appendUserStatusData({'type':'user_status_list','content':None, \
                                                            'name':self.user_name,'thread_from':self.thread_id,\
                                                            'connected':True,'option':'new',\
                                                            'reconnection_count':self.reconnection_count})
        else:
            print(f'client {self.user_name} reconnection successful')
            #broadcast this client user is reconnected
            self.msg_broadcast_thread.appendUserStatusData({'type':'user_status_list','content':None, \
                                                            'name':self.user_name,'thread_from':self.thread_id,\
                                                            'connected':True,'option':'change',\
                                                            'reconnection_count':self.reconnection_count})

        #send client user status list to client
        msg_byte_stream= makeJSONMSG(['type','user_status_list','content',client_list.getUserStatusList(self.thread_id),\
                                      'option','new'])
        return_val=self.sendMsgToClient(msg_byte_stream)
        if return_val==CLIENT_SOCKET_BROKEN:
            #broadcast this client user is disconnected
            self.msg_broadcast_thread.appendUserStatusData({'type':'user_status_list','content':None, \
                                                            'name':self.user_name,'thread_from':self.thread_id,\
                                                            'connected':False,'option':'change',\
                                                            'reconnection_count':self.reconnection_count})
            self.closeAllSocket()
            self.parent.collectorAppend(self)
            return


        #do service
        idle_count=0
        idle_count_max=30 # minimum 3 seconds of idle waiting
        while self.keep_running[0] and not self.thread_stop:
            #first half: receive message from client
            #first receive broadcast message bytestream from client
            broadcast_msg_json= self.recvMsgFromClient(0.1) # after this, connection rebuilding goes based on return val
            if broadcast_msg_json==CLIENT_STOP:
                break
            elif broadcast_msg_json==CLIENT_SOCKET_BROKEN:
                #connection rebuilding goes here: just kill this worker
                #broadcast this client user is disconnected
                self.msg_broadcast_thread.appendUserStatusData({'type':'user_status_list','content':None, \
                                                                'name':self.user_name,'thread_from':self.thread_id,\
                                                                'connected':False,'option':'change',\
                                                                'reconnection_count':self.reconnection_count})
                print(f'client {self.user_name} socket broken')
                self.closeAllSocket()
                self.parent.collectorAppend(self)
                return
            elif broadcast_msg_json==CLIENT_RECV_TIMEOUT or \
                 broadcast_msg_json==CLIENT_RECV_NONE:
                pass
            else:
                idle_count=0 #client idle count reset
                #last broadcast the message to other clients
                print(f'{self.user_name}: {broadcast_msg_json["content"]}')
                self.msg_broadcast_thread.appendMSGData({'type':'broadcast_msg','thread_from':self.thread_id,\
                                                         'name':self.user_name,'msg':broadcast_msg_json['content']})
            
            
##            #first half: receive message from client
##            #first receive broadcast message bytestream from client
##            broadcast_msg=''
##            tmp_msg=''
##            self.conn_socket.settimeout(0.1) # maximum 0.1 seconds waiting
##            while True:
##                try:
##                    #receive header stream
##                    tmp_msg= self.conn_socket.recv(HEADER_LEN).decode('utf-8')
##                except socket.error as e:
##                    #connection rebuilding goes here
##                    break
##                except socket.timeout:
##                    break
##                # check if client program exited
##                if tmp_msg.find(HEADER_CLIENT_END)>=0:
##                    self.thread_stop=True
##                    break
##                header_content, bytes_num_follow, _=tmp_msg.split('|')
##                bytes_num_follow=int(bytes_num_follow)
##                get_next_msg=False
##                if header_content==HEADER_MSG_CONT:
##                    get_next_msg=True
##                    
##                self.conn_socket.settimeout(3) # maximum 3 seconds waiting
##                
##                try:
##                    broadcast_msg+=self.conn_socket.recv(bytes_num_follow).decode('utf-8')
##                except socket.timeout:
##                    #connection rebuilding goes here
##                    pass
##                except socket.error as e:
##                    #connection rebuilding goes here
##                    pass
##                
##                #receive continuing stream if exists
##                while get_next_msg:
##                    tmp_msg=''
##                    try:
##                        tmp_msg= self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8')
##                    except socket.timeout:
##                        #connection rebuilding goes here
##                        pass
##                    except socket.error as e:
##                        #connection rebuilding goes here
##                        pass
##                    header_content, bytes_num_follow, _=tmp_msg.split('|')
##                    bytes_num_follow=int(bytes_num_follow)
##                    if header_content==HEADER_MSG_END:
##                        get_next_msg=False
##
##                    try:
##                        broadcast_msg+=self.conn_socket.recv(bytes_num_follow).decode('utf-8')
##                    except socket.timeout:
##                        #connection rebuilding goes here
##                        pass
##                    except socket.error as e:
##                        #connection rebuilding goes here
##                        pass
##                        
##                self.conn_socket.settimeout(None) # turn connection socket to blocking mode
##
##                #second try to convert received msg to json obj
##                broadcast_msg_json={}
##                try:
##                    broadcast_msg_json= json.loads(broadcast_msg)
##                except json.JSONDecodeError:
##                    #just discard received broadcasted bytestream
##                    continue
##
##                #last broadcast the message to other clients
##                print(f'{self.user_name}: {broadcast_msg_json["content"]}')
##                self.msg_broadcast_thread.appendMSGData({'thread_from':self,'name':self.user_name,'msg':broadcast_msg_json['content']})
##                break
##                
##
##            self.conn_socket.settimeout(None) # turn connection socket to blocking mode

            #pass second half if client thread should stop
            if not self.keep_running or self.thread_stop:
                break            

            #second half: send other clients' messages to client
            while True:               
                other_client_msg_data=None
                #check if there is pending message to send
                
                if len(self.broadcast_msg_list)>0:
                    self.broadcast_msg_list_mutex.lock()
                    other_client_msg_data=self.broadcast_msg_list.pop(0)
                    self.broadcast_msg_list_mutex.unlock()

                if other_client_msg_data is None:
                    break

                #send that message to client
##                byte_stream_index=0
                msg_byte_stream=None
                if other_client_msg_data['type']=='broadcast_msg':
                    msg_byte_stream= makeJSONMSG(['type',other_client_msg_data['type'],'content',other_client_msg_data['msg'], \
                                                  'from_name', other_client_msg_data['name']])
                elif other_client_msg_data['type']=='user_status_list':
                    msg_byte_stream= makeJSONMSG(['type',other_client_msg_data['type'],'content',None, \
                                                 'from_name', other_client_msg_data['name'],\
                                                  'connected', other_client_msg_data['connected'],\
                                                  'option', other_client_msg_data['option']])
                elif other_client_msg_data['type']=='broadcast_file':
                    msg_byte_stream= makeJSONMSG(['type',other_client_msg_data['type'],'content',other_client_msg_data['msg'], \
                                                  'from_name', other_client_msg_data['name'], \
                                                  'file_name', other_client_msg_data['file_name'], \
                                                  'file_id', other_client_msg_data['file_id']])
                return_val= self.sendMsgToClient(msg_byte_stream)
                if return_val==CLIENT_SOCKET_BROKEN:
                    #connection rebuilding goes here
                    #broadcast this client user is disconnected
                    self.msg_broadcast_thread.appendUserStatusData({'type':'user_status_list','content':None, \
                                                                    'name':self.user_name,'thread_from':self.thread_id,\
                                                                    'connected':False,'option':'change',\
                                                                    'reconnection_count':self.reconnection_count})
                    self.closeAllSocket()
                    self.parent.collectorAppend(self)
                    return
##                byte_stream_len= len(msg_byte_stream)
##                try:
##                    while byte_stream_index<byte_stream_len:
##                        if byte_stream_len-byte_stream_index>MAX_BUFFER_LEN-HEADER_LEN:
##                            self.conn_socket.send(makeHeader(HEADER_MSG_CONT,MAX_BUFFER_LEN-HEADER_LEN) + \
##                                msg_byte_stream[byte_stream_index:byte_stream_index+(MAX_BUFFER_LEN-HEADER_LEN)])
##                        else:
##                            self.conn_socket.send(makeHeader(HEADER_MSG_END,byte_stream_len-byte_stream_index) + \
##                                msg_byte_stream[byte_stream_index:byte_stream_len])
##                        byte_stream_index+=MAX_BUFFER_LEN-HEADER_LEN
##                except socket.error as e:
##                    #connection rebuilding goes here
##                    print(e)
##                    pass

                idle_count=0 #client idle count reset after successful sending of messages


            #check if socket is broken while client is idle
            idle_count+=1
            if idle_count>=idle_count_max:
                #check if socket is broken
                print(f'client {self.user_name} is idle')
##                msg_byte_stream= makeJSONMSG(['type','connection_check','content',None])
                return_val= self.checkConnection()
##                return_val= self.sendMsgToClient(msg_byte_stream)
                if return_val==CLIENT_SOCKET_BROKEN:
                    #rebuilding goes here: just kill this worker
                    #broadcast this client user is disconnected
                    self.msg_broadcast_thread.appendUserStatusData({'type':'user_status_list','content':None, \
                                                                    'name':self.user_name,'thread_from':self.thread_id,\
                                                                    'connected':False,'option':'change',\
                                                                    'reconnection_count':self.reconnection_count})
                    print(f' client {self.user_name} connection broken')
                    self.closeAllSocket()
                    self.parent.collectorAppend(self)
                    #here, send signal that the client is disconnected
                    return
                print(f' client {self.user_name} is online')
                idle_count=0
                pass

        #remove this client's name from user name list widget
        self.userEntrySignal.emit({'in':False,'out':True,'name':self.user_name,'thread':self})

        #broadcast this client user is exiting
        self.msg_broadcast_thread.appendUserStatusData({'type':'user_status_list','content':None, \
                                                        'name':self.user_name,'thread_from':self.thread_id, \
                                                        'connected':False,'option':'out',\
                                                        'reconnection_count':self.reconnection_count})

        #send server end header to client
        self.signalServerEndToClient()

        #close socket and remove this worker from global client worker thread list
        self.closeAllSocket()
        self.parent.collectorAppend(self)
        self.removeThisWorker()
        #signal all file workers related
        self.parent.signalAllClientByServerThreadID(self.thread_id)
    
    def stop(self):
        self.thread_stop=True
##        #quit and wait
##        self.quit()
##        self.wait(300) # wait 0.3 seconds

    def checkConnection(self):
        global CLIENT_SOCKET_BROKEN
        global HEADER_CONNECTION_CHECK, HEADER_CIENT_END
        prev_timeout=self.conn_socket.gettimeout()
        self.conn_socket.settimeout(2)
        try:
            self.conn_socket.send(makeHeader(HEADER_CONNECTION_CHECK,0))
            tmp_msg=b''
            while len(tmp_msg)<HEADER_LEN:
                tmp_msg+=self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
            reply_header,bytes_num_follow,_= tmp_msg.decode('utf-8').split("|")
            bytes_num_follow=int(bytes_num_follow)
            self.conn_socket.settimeout(prev_timeout)
            if reply_header==HEADER_CONNECTION_CHECK:
                return True
            elif reply_header==HEADER_CLIENT_END:
                self.thread_stop=True
                return True
            else:
                self.header_reserved=reply_header
                self.bytes_num_follow=bytes_num_follow
                return True
        except socket.timeout:
            self.conn_socket.settimeout(prev_timeout)
            return CLIENT_SOCKET_BROKEN            
        except socket.error as e:
            self.conn_socket.settimeout(prev_timeout)
            return CLIENT_SOCKET_BROKEN

    def sendMsgToClient(self,msg_byte_stream):
        global MAX_BUFFER_LEN, HEADER_LEN
        global CLIENT_SOCKET_BROKEN
        global SEND_MSG_OK
        byte_stream_index=0
        byte_stream_len= len(msg_byte_stream)
        try:
            while byte_stream_index<byte_stream_len:
                if byte_stream_len-byte_stream_index>MAX_BUFFER_LEN-HEADER_LEN:
                    self.conn_socket.send(makeHeader(HEADER_MSG_CONT,MAX_BUFFER_LEN-HEADER_LEN) + \
                        msg_byte_stream[byte_stream_index:byte_stream_index+(MAX_BUFFER_LEN-HEADER_LEN)])
                else:
                    self.conn_socket.send(makeHeader(HEADER_MSG_END,byte_stream_len-byte_stream_index) + \
                        msg_byte_stream[byte_stream_index:byte_stream_len])
                byte_stream_index+=MAX_BUFFER_LEN-HEADER_LEN
        except socket.error as e:
            #connection rebuilding goes here
            print(e)
            return CLIENT_SOCKET_BROKEN
        return SEND_MSG_OK

    def recvMsgFromClient(self,first_timeout):
        global HEADER_MSG_CONT, HEADER_MSG_END
        global HEADER_CLIENT_END, HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global CLIENT_STOP, CLIENT_RECV_NONE
        global CLIENT_RECV_TIMEOUT, CLIENT_SOCKET_BROKEN
        prev_timeout=self.conn_socket.gettimeout()
        #first receive broadcast message bytestream from client
        broadcast_msg=''
        tmp_msg=''
        self.conn_socket.settimeout(first_timeout) # maximum 'first_timeout' seconds waiting
        header_content, bytes_num_follow=None,None
        if self.header_reserved is None:
            try:
                #receive header stream
                tmp_msg=b''
                while len(tmp_msg)<HEADER_LEN:
                    tmp_msg+=self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
                tmp_msg= tmp_msg.decode('utf-8')
            except socket.timeout:
                return CLIENT_RECV_NONE
            except socket.error as e:
                #connection rebuilding goes here
                return CLIENT_SOCKET_BROKEN
            
            header_content, bytes_num_follow, _=tmp_msg.split('|')
            bytes_num_follow=int(bytes_num_follow)
        else:
            header_content=self.header_reserved
            bytes_num_follow=self.bytes_num_follow
            self.header_reserved=None
            self.bytes_num_follow=None

        # check if client program exited
        if header_content==HEADER_CLIENT_END:
            self.thread_stop=True
            return CLIENT_STOP

        #check if connection check header remaining
        if header_content==HEADER_CONNECTION_CHECK:
            return CLIENT_RECV_NONE
        
        get_next_msg=False
        if header_content==HEADER_MSG_CONT:
            get_next_msg=True

        
            
            
        self.conn_socket.settimeout(0.5) # maximum 0.5 seconds waiting
        
        try:
            tmp_bytestream=b''
            while len(tmp_bytestream)<bytes_num_follow:
                tmp_bytestream+=self.conn_socket.recv(bytes_num_follow-len(tmp_bytestream))
            broadcast_msg+=tmp_bytestream.decode('utf-8')
        except socket.timeout:
            #connection rebuilding goes here
            return CLIENT_SOCKET_BROKEN
        except socket.error as e:
            #connection rebuilding goes here
            return CLIENT_SOCKET_BROKEN
        
        #receive continuing stream if exists
        while get_next_msg:
            tmp_msg=''
            try:
                tmp_msg=b''
                while len(tmp_msg)<HEADER_LEN:
                    tmp_msg+=self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
                tmp_msg= tmp_msg.decode('utf-8')
            except socket.timeout:
                #connection rebuilding goes here
                return CLIENT_SOCKET_BROKEN
            except socket.error as e:
                #connection rebuilding goes here
                return CLIENT_SOCKET_BROKEN
            header_content, bytes_num_follow, _=tmp_msg.split('|')
            bytes_num_follow=int(bytes_num_follow)
            if header_content==HEADER_MSG_END:
                get_next_msg=False

            try:
                tmp_bytestream=b''
                while len(tmp_bytestream)<bytes_num_follow:
                    tmp_bytestream+=self.conn_socket.recv(bytes_num_follow-len(tmp_bytestream))
                broadcast_msg+=tmp_bytestream.decode('utf-8')
            except socket.timeout:
                #connection rebuilding goes here
                return CLIENT_SOCKET_BROKEN
            except socket.error as e:
                #connection rebuilding goes here
                return CLIENT_SOCKET_BROKEN
                
        self.conn_socket.settimeout(prev_timeout) # prev timeout restore

        #second try to convert received msg to json obj
        broadcast_msg_json={}
        try:
            broadcast_msg_json= json.loads(broadcast_msg)
        except json.JSONDecodeError:
            #just discard received broadcasted bytestream
            return CLIENT_RECV_NONE
        return broadcast_msg_json

    def signalServerEndToClient(self):
        global HEADER_SERVER_END
        try:
            self.conn_socket.send(makeHeader(HEADER_SERVER_END,0))
        except socket.error as e:
            pass
    
    def closeAllSocket(self):
        try:
            if self.conn_socket.fileno()>=0:
                self.conn_socket.close()
        except socket.error as e:
            pass
    def removeThisWorker(self):
        global client_list
        if self.thread_id is None:
            return
        client_list.removeEntry(self)

    def setThreadID(self,thread_id):
        self.thread_id=thread_id

    def setReconnectionCount(self,reconnection_count):
        self.reconnection_count=reconnection_count

    def appendBroadcastMSG(self,msg):
        self.broadcast_msg_list_mutex.lock()
        self.broadcast_msg_list.append(msg)
        self.broadcast_msg_list_mutex.unlock()

class file_listener(QThread):
    new_file_connection= pyqtSignal(dict)
    def __init__(self,parent):
        global keep_running
        super().__init__()
        self.parent=parent
        self.server_port=None
        self.file_server_port=None
        self.keep_running=keep_running
        self.file_server_socket=None

        #variables and array for key making
        self.key=None
        self.key_len=20
        self.key_char_list=[]
        #lower case alphabet
        ord_num=ord('a')
        while ord_num<=ord('z'):
            self.key_char_list.append(chr(ord_num))
            ord_num+=1
        #upper case alphabet
        ord_num=ord('A')
        while ord_num<=ord('Z'):
            self.key_char_list.append(chr(ord_num))
            ord_num+=1
        #digits
        ord_num=ord('0')
        while ord_num<=ord('9'):
            self.key_char_list.append(chr(ord_num))
            ord_num+=1

    def run(self):
        print(f'file_listener socket num: {self.file_server_socket}')
        while self.keep_running[0]:
            while self.keep_running[0] and self.parent.clientThreadListFull():
                time.sleep(0.1)
            try:
                conn_socket,addr= self.file_server_socket.accept()

                #do password check: no encryption << in worker thread?
                #update client list

                # make client worker thread and append to list
                # make worker
                conn_data={'conn_socket':conn_socket,'ip_addr':addr[0],'file_transfer_key':self.key}
##                clientWorker(conn_socket,addr,self.pw).start()
                self.new_file_connection.emit(conn_data)
##                self.parent.startClientWorker(conn_socket,addr,self.pw)
            except socket.timeout as e:
##                print('file_listener_working')
                continue
            except socket.error as e:
                # show small window while exiting
                print(e)
                print('unexpected socket error occurred\nterminating...')
                break
            
        #close server socket
        self.closeAllSocket()

    def canMakeFileServerSocket(self):
        global PORT_DISTANCE_UNIT
        global MAX_LISTEN, ACCEPT_TIMEOUT
        global PORT_IN_USE_ERROR
        max_trial=200
        trial_count=0
        file_port_num=self.server_port
        while trial_count<max_trial:
            try:
                file_port_num+=PORT_DISTANCE_UNIT
                file_server_socket= socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                file_server_socket.bind(('0.0.0.0',file_port_num))
                file_server_socket.listen(MAX_LISTEN)
                file_server_socket.settimeout(ACCEPT_TIMEOUT)
                self.file_server_socket=file_server_socket
                self.file_server_port=file_port_num
                return True
                pass
            except Exception as e:
                pass
            trial_count+=1
        # if all trial fails, the server cannot start in short while
        return PORT_IN_USE_ERROR

    def makeKey(self):
        self.key=''
        key_char_num=len(self.key_char_list)
        for i in range(self.key_len):
            self.key+=self.key_char_list[random.randrange(0,key_char_num)]

    def getKey(self):
        return self.key

    def getFileServerPort(self):
        return self.file_server_port

    def setServerPort(self,server_port):
        self.server_port=server_port

    def stop(self):
        global keep_running_mutex
        keep_running_mutex.lock()
        self.keep_running[0]=False
        keep_running_mutex.unlock()

    def closeAllSocket(self):
        try:
            self.file_server_socket.close()
        except socket.error as e:
            pass
        self.file_server_socket=None

class listener(QThread):
    new_connection= pyqtSignal(dict)

    def __init__(self, parent):
        global client_list, keep_running
        super().__init__()
        self.parent=parent
        self.port= None
        self.pw= None
        self.server_socket=None
        self.keep_running=keep_running
        self.client_list=client_list

    def run(self):
        while self.keep_running[0]:
            while self.keep_running[0] and self.parent.clientThreadListFull():
                time.sleep(0.1)
            try:
                conn_socket,addr= self.server_socket.accept()

                #do password check: no encryption << in worker thread?
                #update client list

                # make client worker thread and append to list
                # make worker
                conn_data={'conn_socket':conn_socket,'ip_addr':addr[0],'pw':self.pw}
##                clientWorker(conn_socket,addr,self.pw).start()
                self.new_connection.emit(conn_data)
##                self.parent.startClientWorker(conn_socket,addr,self.pw)
            except socket.timeout as e:
                continue
            except socket.error as e:
                # show small window while exiting
                print(e)
                print('unexpected socket error occurred\nterminating...')
                break

        self.client_list.signalAllClientWorkers()

        #here, should clear client list in gui

        #close server socket
        self.closeAllSocket()
               
    def canMakeServerSocket(self,port,pw):
        global PORT_NUM_ERROR, PORT_IN_USE_ERROR, ACCEPT_TIMEOUT
        # check if given port is valid int
        try:
            self.port= int(port)
            self.pw= pw
        except Exception as e:
            #alert message here
            return PORT_NUM_ERROR

        # try to open server socket
        try:
            server_socket= socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            server_socket.bind(('0.0.0.0',self.port))
            server_socket.listen(MAX_LISTEN)
            server_socket.settimeout(ACCEPT_TIMEOUT)
            self.server_socket=server_socket
        except Exception as e:
            #pop up alert message
            return PORT_IN_USE_ERROR
        # return True when successfuly made server socket
        return True

    def setPortAndPassword(self,port,pw):
        self.port=port
        self.pw=pw

##    def signalAllClientWorkers(self):
##        global client_workers_mutex
##        client_workers_mutex.lock()
##
##        for i in range(len(self.client_workers)-1,-1,-1):
##            client_workers[i].stop()
##            client_workers.pop(-1)
##
##        client_workers_mutex.unlock()

    def stop(self):
        global keep_running_mutex
        keep_running_mutex.lock()
        self.keep_running[0]=False
        keep_running_mutex.unlock()
##        #close server socket
##        try:
##            if self.server_socket.fileno()>=0:
##                self.server_socket.close()
##        except socket.error as e:
##            pass
##        #quit and wait
##        print('listner stop bp')
##        self.quit()
##        self.wait(2000) # wait 2 seconds
    def closeAllSocket(self):
        try:
##            if self.server_socket.fileno()>=0:
##                self.server_socket.close()
            self.server_socket.close()
        except socket.error as e:
            pass
        self.server_socket=None

def get_public_ip():
    ip_address='cannot find public IP'
    try:
        ip_address=get('https://api.ipify.org').content.decode('utf-8')
    except:
        pass
    return ip_address

class dialogWindow(QDialog, dialog_form_class):
    def __init__(self,msg):
        super().__init__()
        self.setupUi(self)
        self.setFixedSize(self.size())
        self.label.clear()
        self.label.setText(msg)
        self.label.setAlignment(Qt.AlignCenter)
        self.okButton.clicked.connect(lambda: self.close())

class serverPromptWindow(QMainWindow, server_form_class):
    def __init__(self):
        global SERVER_STATE_STOPPED
        super().__init__()
        self.setupUi(self)
##        self.localIPEdit.setReadOnly(True)
        self.localIPEdit.setText(socket.gethostbyname(socket.gethostname()))
##        self.localIPEdit.setStyleSheet("""
##                QLineEdit {
##                    background-color: rgb(204,204,204)
##                }
##            """) # set ip address box background color as gray
        self.lineEditDisable(self.localIPEdit)
        self.externalIPEdit.setText(get_public_ip())
##        self.externalIPEdit.setStyleSheet("""
##                QLineEdit {
##                    background-color: rgb(204,204,204)
##                }
##            """) # set ip address box background color as gray
        self.lineEditDisable(self.externalIPEdit)

        self.startButton.clicked.connect(self.serverStart)
        self.stopButton.clicked.connect(self.serverStop)

        self.stopButton.setDisabled(True) # stop button is disabled first

        #fix window size
        self.setFixedSize(self.size())

        self.pw='' #server password

        #thread for listening to server port
        self.listener_thread=None

        #thread for listening to file server port
        self.file_listener_thread=None

        #thread for broadcasting clients' messages to each other
        self.msg_broadcast_thread=None

        #enable/disable window close
        self.close_enabled=True

        #userNameList mutex
        self.list_mutex= QMutex()

        #temporary client thread pointer
        self.tmp_client_thread_pointer= None

        #client thread collector thread
        self.client_thread_collector_thread=None

        #temporary client thread reservoir
        self.tmp_client_thread_list=[]
        self.tmp_client_thread_list_max_len=100
        self.tmp_client_thread_list_mutex=QMutex()

        #base file path
        self.base_file_path=os.getcwd()

        #file map list
        self.file_map_list= fileMapList()

    def serverStart(self):
        global PORT_NUM_ERROR, PORT_IN_USE_ERROR, PW_INVALID
        global password_regex, keep_running_mutex
        self.DisableAllButton() #disable all button while starting server
        # set keep running as True
        keep_running_mutex.lock()
        keep_running[0]=True
        keep_running_mutex.unlock()
        
        if self.listener_thread is None:
            self.listener_thread=listener(self)
            self.listener_thread.new_connection.connect(self.startClientWorker)

        if self.file_listener_thread is None:
            self.file_listener_thread=file_listener(self)
            self.file_listener_thread.new_file_connection.connect(self.startFileClientWorker)

        if self.msg_broadcast_thread is None:
            self.msg_broadcast_thread= msgBroadcastWorker(self)

        if self.client_thread_collector_thread is None:
            self.client_thread_collector_thread= threadCollectWorker(self)
        
        #first check if password is valid
        if not password_regex.match(self.pwEdit.text()):
            self.EnableAllButton() #enable buttons
            #show dialog that password is invalid
            dlg=dialogWindow('server start process failed\n:invalid password\n:alphabet, digit, !,@,#,%,& and * are allowed\n:empty password is not allowed')
            dlg.setWindowTitle('server dialog')
            dlg.exec()
            return
        #second try to make server socket
        ret_val=self.listener_thread.canMakeServerSocket(self.portEdit.text(),self.pwEdit.text())
        if ret_val==1:
            self.file_listener_thread.setServerPort(int(self.portEdit.text()))
            ret_val=self.file_listener_thread.canMakeFileServerSocket()
            if ret_val==PORT_IN_USE_ERROR:
                self.listen_thread.closeAllSocket()
                self.EnableAllButton() #enable buttons
                #show dialog that tells server can't be started
                dlg=dialogWindow('server start process failed\n:there are few ports enable')
                dlg.setWindowTitle('server dialog')
                dlg.exec()
                return
            self.file_listener_thread.makeKey() # key for transferring file
            print(f'file transfer key: {self.file_listener_thread.getKey()}')
            self.pw= self.pwEdit.text()
            self.listener_thread.setPortAndPassword(int(self.portEdit.text()),self.pw)
            self.listener_thread.start()
            self.file_listener_thread.start()
            self.msg_broadcast_thread.start() # start msg broadcast thread also
            self.client_thread_collector_thread.start() # start client thread collector thread also
            self.EnableAllButton() #enable buttons
            # disable start button and enable stop button
            self.startButton.setDisabled(True)
            self.stopButton.setEnabled(True)
            #disable editting port and password
            self.lineEditDisable(self.portEdit)
            self.lineEditDisable(self.pwEdit)
            #show dialog that tells server is started
            dlg=dialogWindow('server has started successfully')
            dlg.setWindowTitle('server dialog')
            dlg.exec()
            return
        elif ret_val==PORT_NUM_ERROR:
            self.EnableAllButton() #enable buttons
            #show dialog that tells server can't be started
            dlg=dialogWindow('server start process failed\n:your port number input is not an integer value')
            dlg.setWindowTitle('server dialog')
            dlg.exec()
            return
        else:
            self.EnableAllButton() #enable buttons
            #show dialog that tells server can't be started
            dlg=dialogWindow('server start process failed\n:your port number is already in use')
            dlg.setWindowTitle('server dialog')
            dlg.exec()
            return

            
    def serverStop(self):
        self.DisableAllButton() #disable all button while starting server
        
##        self.tmp_client_thread_pointer= None #flush temporary client thread pointer

        #stop and delete listener thread
        self.listener_thread.stop()
        self.listener_thread.wait()
        del self.listener_thread
        self.listener_thread=None

        #stop and delete file listener thread
        self.file_listener_thread.stop()
        self.file_listener_thread.wait()
        del self.file_listener_thread
        self.file_listener_thread=None

        #stop and delete msg broadcast thread
        self.msg_broadcast_thread.stop()
        self.msg_broadcast_thread.wait()
        del self.msg_broadcast_thread
        self.msg_broadcast_thread= None

        #clear client list
        self.list_mutex.lock()
        self.userNameList.clear()
        self.list_mutex.unlock()

        print('stop bp')

        #stop and delete client threads waiting in tmp list
        self.tmp_client_thread_list_mutex.lock()
        while len(self.tmp_client_thread_list)>0:
            time.sleep(0.1)
        self.tmp_client_thread_list_mutex.unlock()
        
        #also stop and wait client thread collector thread
        #this process should be in correct order
        self.client_thread_collector_thread.stop()
        self.client_thread_collector_thread.wait()
        del self.client_thread_collector_thread
        self.client_thread_collector_thread = None

        print('stop bp2')

        
        self.EnableAllButton() #enable buttons
        # disable stop button and enable start button
        self.stopButton.setDisabled(True)
        self.startButton.setEnabled(True)
        dlg=dialogWindow('server has stopped successfully')
        dlg.setWindowTitle('server dialog')
        dlg.exec()

        self.lineEditEnable(self.portEdit)
        self.lineEditEnable(self.pwEdit)

    def startClientWorker(self, conn_data):
        client_thread= clientWorker(self,conn_data['conn_socket'],conn_data['ip_addr'],conn_data['pw'], \
                                    self.msg_broadcast_thread,self.file_listener_thread.getFileServerPort(),\
                                    self.file_listener_thread.getKey())
        client_thread.userEntrySignal.connect(self.handleUserEntrySignal)
##        print('sCW before start')
        client_thread.confirmSignal.connect(self.handleConfirmSignal)
        client_thread.start()
##        self.tmp_client_thread_pointer= client_thread # save client thread to temporary pointer
        self.tmp_client_thread_list_mutex.lock()
        self.tmp_client_thread_list.append(client_thread)
        self.tmp_client_thread_list_mutex.unlock()
##        print('sCW after start')

    def handleConfirmSignal(self, confirm_info):
        if not confirm_info['validation_success']:
            #append thread to collector list
            self.client_thread_collector_thread.appendThread(confirm_info['thread'])
        self.clientThreadListRemove(confirm_info['thread'])
        

    def handleUserEntrySignal(self, entry_info):
        # add/remove user name to/from client list
        if entry_info['in']==True:
            #server namelist table update
            self.list_mutex.lock()
            self.userNameList.addItem(entry_info['name'])
            self.list_mutex.unlock()           
        elif entry_info['out']==True:
            self.list_mutex.lock()
            for i in range(self.userNameList.count()):
                if self.userNameList.item(i).text()==entry_info['name']:
                    self.userNameList.takeItem(i)
                    break
            self.list_mutex.unlock()

    def startFileClientWorker(self, conn_data):
        global file_client_list
        file_transfer_thread=fileClientWorker(self,conn_data['conn_socket'],conn_data['ip_addr'],\
                                              self.msg_broadcast_thread, self.client_thread_collector_thread,\
                                              conn_data['file_transfer_key'], self.base_file_path)
        file_transfer_thread.resultSignal.connect(self.handleFileTransferResult)
##        file_client_list.appendEntry(file_transfer_thread)
        file_transfer_thread.start()
        self.tmp_client_thread_list_mutex.lock()
        self.tmp_client_thread_list.append(file_transfer_thread)
        self.tmp_client_thread_list_mutex.unlock()

    def handleFileTransferResult(self, result_info):
        if not result_info['validation_success']:
            #append thread to collector list
            self.client_thread_collector_thread.appendThread(confirm_info['thread'])
        self.clientThreadListRemove(result_info['thread'])

    def lineEditEnable(self,lineEdit):
        lineEdit.setReadOnly(False)
        lineEdit.setStyleSheet("""
                QLineEdit {
                    background-color: rgb(255,255,255)
                }
            """)

    def lineEditDisable(self,lineEdit):
        lineEdit.setReadOnly(True)
        lineEdit.setStyleSheet("""
                QLineEdit {
                    background-color: rgb(204,204,204)
                }
            """)

    def EnableAllButton(self):
        self.startButton.setEnabled(True)
        self.stopButton.setEnabled(True)
        self.close_enabled=True
    def DisableAllButton(self):
        self.close_enabled=False
        self.startButton.setDisabled(True)
        self.stopButton.setDisabled(True)

    def closeEvent(self,event):
        if self.close_enabled:
            super(serverPromptWindow,self).closeEvent(event)
        else:
            event.ignore()

    def clientThreadListFull(self):
        return len(self.tmp_client_thread_list)>=self.tmp_client_thread_list_max_len

    def clientThreadListAppend(self,thread):
        self.tmp_client_thread_list_mutex.lock()
        self.tmp_client_thread_list.append(thread)
        self.tmp_client_thread_list_mutex.unlock()

    def clientThreadListRemove(self,target_thread):
        self.tmp_client_thread_list_mutex.lock()
        for i in range(len(self.tmp_client_thread_list)):
            thread=self.tmp_client_thread_list[i]
            if thread is target_thread:
                self.tmp_client_thread_list.pop(i)
                break
        self.tmp_client_thread_list_mutex.unlock()

    def collectorAppend(self,thread):
        self.client_thread_collector_thread.appendThread(thread)

    def getFileIDAndRealName(self,file_name,user_name):
        return self.file_map_list.getFileIDAndRealName(file_name,user_name)

    def getRealFileNameByID(self,target_id):
        return self.file_map_list.getRealFileNameByID(target_id)

    def signalAllClientByServerThreadID(self,server_thread_id):
        global file_client_list
        file_client_list.signalAllClientByServerThreadID(server_thread_id)

    def prtpwd(self):
        print(f'local ip: {self.localIPEdit.text()}')
        print(f'external ip: {self.externalIPEdit.text()}')
        print(f'port: {self.portEdit.text()}')
        print(f'password: {self.pwEdit.text()}')

##    def send_msg(self):
##        print("you:\b",self.textEdit.toPlainText())
##        self.textEdit.setPlainText('')
##
##    def send_msg_by_click(self):
##        print("you:",self.lineEdit.text())
##        self.lineEdit.setText('')
##
##    def send_msg_by_return(self):
##        print("you:",self.lineEdit.text())
##        self.lineEdit.setText('')
##
##    def printCurPos(self):
##        print("curPos:",self.lineEdit.cursorPosition())
##
##    def printSelEnd(self):
##        print("selStart:",self.lineEdit.selectionStart())
##        print("selEnd:",self.lineEdit.selectionEnd())
##
##    def addNewLine(self):
##        self.lineEdit.append('\n')
##
##    def eventFilter(self,obj,event):
##        if event.type() == QEvent.KeyPress and obj is self.textEdit:
##            if event.key() in [Qt.Key_Return, Qt.Key_Enter] and self.textEdit.hasFocus():
##                self.send_msg()
##        return super(something,self).eventFilter(obj,event)

def myExceptionHook(exctype,value,traceback):
    print(exctype,value,traceback)

    sys._excepthook(exctype,value,traceback)

if __name__=='__main__':
    sys._excepthook = sys.excepthook
    sys.excepthook = myExceptionHook
    
    app= QApplication(sys.argv)
    window= serverPromptWindow()
    window.show()
    app.exec_()
