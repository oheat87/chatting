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

import time

try:
    from requests import get
except ModuleNotFoundError:
    install('requests')

import re
import json
import os

#CONSTANTS
MAX_LISTEN= 10
MAX_BUFFER_LEN= 1024

ACCEPT_TIMEOUT= 0.1
RECV_TIMEOUT=0.2

PORT_NUM_ERROR=2
MAKE_SOCKET_ERROR=3
PW_INVALID=4
PW_INCORRECT=5
NAME_INVALID=6
SOCKET_BROKEN=7
NAME_DUPLICATED=8
LOGIN_OK=9
ILLEGAL_RECONNECTION=10
RECONNECTION_FAIL=11
SERVER_STOP=12
SERVER_RECV_NONE=13
SERVER_RECV_TIMEOUT=14
KEY_INCORRECT=15
NAME_UNREGISTERED=16
CANNOT_MAKE_FILE=17
FILE_TRANSFER_OK=18
FILE_TRANSFER_FAIL=19
FILE_TRANSFER_COMPLETE=20
SELF_STOP=21
FILE_WRITE_FAIL=22
SEND_MSG_OK=23



MSG_BOX_PAD_VERT=10
MSG_BOX_PAD_HORZ=10
MSG_ADDITIONAL_SPACE=20
WIDGET_PAD_VERT= 30

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
HEADER_SERVER_END='server_end'
HEADER_CONNECTION_CHECK='connection_check'
HEADER_USER_STATUS='user_status'

#global variable
chat_count=0
name_list=['John','Doe','paul','artreides']
serverIP=''
serverPort=None
pw=''
name=''



##SERVER_STATE_STARTED=0
##SERVER_STATE_STOPPED=1

#mutex lock
keep_running_mutex=QMutex()
client_workers_mutex=QMutex()

socket_send_mutex= QMutex()

#global variables
keep_running=[True]
client_workers=[]

dialog_form_class = uic.loadUiType("dialog.ui")[0]
conn_form_class = uic.loadUiType("connDialog.ui")[0]
chat_form_class = uic.loadUiType("chatBox.ui")[0]
login_form_class = uic.loadUiType("login.ui")[0]

password_regex= re.compile('[a-zA-Z0-9!@#%&*]+')
name_regex= re.compile('[a-zA-Z0-9_]+')

##class AltEnterSignal(QObject):

class fileTransferWorker(QThread):
    progressSignal= pyqtSignal(dict)
    resultSignal= pyqtSignal(dict) #signal for uploading file
    def __init__(self,parent,file_path,ip_addr,file_server_port,file_transfer_key,user_name,server_thread_id, \
                 layout,progress_bar_layout,file_download=False,download_button=None,file_id=None):
        global keep_running
        super().__init__()
        self.parent=parent
        self.file_path=file_path
        self.ip_addr=ip_addr
        self.file_server_port=file_server_port
        self.file_transfer_key=file_transfer_key
        self.user_name=user_name
        self.server_thread_id=server_thread_id
        self.layout=layout
        self.progress_bar_layout=progress_bar_layout
        self.keep_running=keep_running
        self.thread_stop=False

        self.conn_socket=None
        self.file=None
        self.file_size=None

        #file transfer progress unit
        self.progress_byte_unit=200000

        #file downlaod variables
        self.file_download= file_download
        self.download_button= download_button
        self.file_id= file_id

    def run(self):
        if not self.file_download:
            self.doFileTransfer()
            return
        else:
            self.doFileDownload()
            return

    def doFileDownload(self):
        global MAKE_SOCKET_ERROR, SOCKET_BROKEN
        global SERVER_STOP, KEY_INCORRECT
        global NAME_UNREGISTERED, CANNOT_MAKE_FILE
        global FILE_TRANSFER_OK, FILE_WRITE_FAIL
        global FILE_TRANSFER_FAIL, FILE_TRANSFER_COMPLETE
        global SELF_STOP
        global SERVER_RECV_NONE, SERVER_RECV_TIMEOUT

        #first try to open file
        self.file=None
        try:
            self.file= open(self.file_path,'wb')
        except:
            print('file open fail')
            self.parent.safeRemoveTmpWorker(self)
            self.resultSignal.emit({'success':False, 'layout':self.layout,\
                                     'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'download', \
                                    'download_button':self.download_button}) #client thread handling
            return

        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            self.parent.safeRemoveTmpWorker(self)
            return
        
        #second try to make socket
        return_val=self.canMakeFileTransferSocket()
        if return_val==MAKE_SOCKET_ERROR:
            print('make socket fail')
            self.parent.safeRemoveTmpWorker(self)
            self.resultSignal.emit({'success':False, 'layout':self.layout,\
                                    'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'download', \
                                    'download_button':self.download_button}) #client thread handling
            self.closeAllSocket()
            self.closeFile()
            return

        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            self.parent.safeRemoveTmpWorker(self)
            return

        #third key and name check
        return_val= self.keyAndNameCheck(upload=False)
        if return_val != FILE_TRANSFER_OK:
            print('key and name check fail')
            self.parent.safeRemoveTmpWorker(self)
            self.resultSignal.emit({'success':False, 'layout':self.layout,\
                                    'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'download', \
                                    'download_button':self.download_button}) #client thread handling
            self.closeAllSocket()
            self.closeFile()
            return

        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            self.parent.safeRemoveTmpWorker(self)
            return

        #last, download file
        return_val= self.downloadFile(self.file,3)
        if return_val==FILE_TRANSFER_COMPLETE:
            #do something
            self.resultSignal.emit({'success':True, 'layout':self.layout,\
                                    'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'download', \
                                    'download_button':self.download_button}) #client thread handling
        elif return_val==SELF_STOP:
            self.parent.safeRemoveTmpWorker(self)
            return
        else:
            #do something
            print('file transfer fail')
            self.resultSignal.emit({'success':False, 'layout':self.layout,\
                                    'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'download', \
                                    'download_button':self.download_button}) #client thread handling

        self.closeAllSocket()
        self.closeFile()
        self.parent.safeRemoveTmpWorker(self)

    def downloadFile(self,file,timeout):
        global HEADER_MSG_CONT, HEADER_MSG_END
        global HEADER_SERVER_END, HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global SERVER_STOP, SERVER_RECV_NONE
        global SERVER_RECV_TIMEOUT, SOCKET_BROKEN
        global SELF_STOP, FILE_WRITE_FAIL
        global SEND_MSG_OK
        global FILE_TRANSFER_COMPLETE
        global FILE_TRANSFER_FAIL_MSG, FILE_TRANSFER_COMPLETE_MSG
        #progress bar variables
        byte_written=0
        byte_prev_written_units=0
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
            return SERVER_RECV_NONE
        except socket.error as e:
            return SOCKET_BROKEN
        except Exception as e:
            print(e)
            print(f'tmp_msg: {tmp_msg}')
            try:
                self.sendMsgToServer(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_FAIL_MSG]))
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
            file.write(tmp_bytestream)
            byte_written+=bytes_num_follow
            tmp_cal=byte_written//self.progress_byte_unit
            if tmp_cal>byte_prev_written_units:
                byte_prev_written_units=tmp_cal
                self.progressSignal.emit({'progress_rate':byte_written/self.file_size,\
                                         'progress_bar_layout':self.progress_bar_layout})
        except socket.timeout:
            return SOCKET_BROKEN
        except socket.error as e:
            return SOCKET_BROKEN
        except Exception as e:
            print(e)
            print('cannot write to file')
            try:
                self.sendMsgToServer(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_FAIL_MSG]))
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
                return SOCKET_BROKEN
            except socket.error as e:
                return SOCKET_BROKEN
            except Exception as e:
                print(e)
                print(f'tmp_msg: {tmp_msg}')
                try:
                    self.sendMsgToServer(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_FAIL_MSG]))
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
                file.write(tmp_bytestream)
                byte_written+=bytes_num_follow
                tmp_cal=byte_written//self.progress_byte_unit
                if tmp_cal>byte_prev_written_units:
                    byte_prev_written_units=tmp_cal
                    self.progressSignal.emit({'progress_rate':byte_written/self.file_size,\
                                             'progress_bar_layout':self.progress_bar_layout})
            except socket.timeout:
                return SOCKET_BROKEN
            except socket.error as e:
                return SOCKET_BROKEN
            except Exception as e:
                print(e)
                try:
                    self.sendMsgToServer(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_FAIL_MSG]))
                except:
                    pass
                return FILE_WRITE_FAIL
                
##        try:
##            self.conn_socket.send(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_COMPLETE_MSG]))
##        except Exception as e:
##            return SOCKET_BROKEN
        return_val= self.sendMsgToServer(makeJSONMSG(['type','file_transfer','content',FILE_TRANSFER_COMPLETE_MSG]))
        if return_val != SEND_MSG_OK:
            return SOCKET_BROKEN
        self.conn_socket.settimeout(prev_timeout) # prev timeout restore
        return FILE_TRANSFER_COMPLETE

    def doFileTransfer(self):
        global MAKE_SOCKET_ERROR, SOCKET_BROKEN
        global SERVER_STOP, KEY_INCORRECT
        global NAME_UNREGISTERED, CANNOT_MAKE_FILE
        global FILE_TRANSFER_OK
        global FILE_TRANSFER_FAIL, FILE_TRANSFER_COMPLETE
        global SELF_STOP

        #first try to open file
        self.file=None
        try:
            self.file= open(self.file_path,'rb')
            self.file_size=os.path.getsize(self.file_path)
        except:
            print('file open fail')
            self.parent.safeRemoveTmpWorker(self)
            self.resultSignal.emit({'success':False, 'layout':self.layout,\
                                     'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'upload'}) #client thread handling
            return

        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            self.parent.safeRemoveTmpWorker(self)
            return
        
        #second try to make socket
        return_val=self.canMakeFileTransferSocket()
        if return_val==MAKE_SOCKET_ERROR:
            print('make socket fail')
            self.parent.safeRemoveTmpWorker(self)
            self.resultSignal.emit({'success':False, 'layout':self.layout,\
                                     'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'upload'}) #client thread handling
            self.closeAllSocket()
            self.closeFile()
            return

        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            self.parent.safeRemoveTmpWorker(self)
            return

        #third key and name check
        return_val= self.keyAndNameCheck()
        if return_val != FILE_TRANSFER_OK:
            print('key and name check fail')
            self.parent.safeRemoveTmpWorker(self)
            self.resultSignal.emit({'success':False, 'layout':self.layout,\
                                     'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'upload'}) #client thread handling
            self.closeAllSocket()
            self.closeFile()
            return

        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            self.parent.safeRemoveTmpWorker(self)
            return

        #last, transfer file
        return_val= self.transferFile(self.file)
        if return_val==FILE_TRANSFER_COMPLETE:
            #do something
            self.resultSignal.emit({'success':True, 'layout':self.layout,\
                                     'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'upload'}) #client thread handling
        elif return_val==SELF_STOP:
            self.parent.safeRemoveTmpWorker(self)
            return
        else:
            #do something
            print('file transfer fail')
            self.resultSignal.emit({'success':False, 'layout':self.layout,\
                                     'progress_bar_layout':self.progress_bar_layout,\
                                    'type':'upload'}) #client thread handling

        self.closeAllSocket()
        self.closeFile()
        self.parent.safeRemoveTmpWorker(self)

    def transferFile(self,file):
        global MAX_BUFFER_LEN, HEADER_LEN
        global SOCKET_BROKEN, SERVER_STOP
        global SELF_STOP
        global FILE_TRANSFER_FAIL, FILE_TRANSFER_COMPLETE
        global FILE_TRANSFER_FAIL_MSG, FILE_TRANSFER_COMPLETE_MSG
        global HEADER_SERVER_END
##        #first send file name
##        file_name=os.path.split(self.file_path)[1]
##        byte_stream_index=0
##        msg_byte_stream= makeJSONMSG(['type','file_name_transfer','content',file_name])
##        byte_stream_len= len(msg_byte_stream)
##        try:
##            while byte_stream_index<byte_stream_len:
##                if byte_stream_len-byte_stream_index>MAX_BUFFER_LEN-HEADER_LEN:
##                    self.conn_socket.send(makeHeader(HEADER_MSG_CONT,MAX_BUFFER_LEN-HEADER_LEN) + \
##                        msg_byte_stream[byte_stream_index:byte_stream_index+(MAX_BUFFER_LEN-HEADER_LEN)])
##                else:
##                    self.conn_socket.send(makeHeader(HEADER_MSG_END,byte_stream_len-byte_stream_index) + \
##                        msg_byte_stream[byte_stream_index:byte_stream_len])
##                byte_stream_index+=MAX_BUFFER_LEN-HEADER_LEN
##        except socket.error:
##            return SOCKET_BROKEN


        #check if this thread should stop
        if self.checkStopAndClose()==SELF_STOP:
            return SELF_STOP

        #second send file byte stream
        prev_timeout=self.conn_socket.gettimeout()
        self.conn_socket.settimeout(5)
        try:
            byte_sent=0
            byte_prev_sent_units=0
            while self.keep_running[0] and not self.thread_stop:
                #send file byte stream
                file_data=file.read(MAX_BUFFER_LEN-HEADER_LEN)
                header=None
                if not file_data:
                    header= makeHeader(HEADER_MSG_END,len(file_data))
                else:
                    header= makeHeader(HEADER_MSG_CONT,len(file_data))
                self.conn_socket.send(header + file_data)
                byte_sent+=len(file_data)
                tmp_cal=byte_sent//self.progress_byte_unit
                if tmp_cal>byte_prev_sent_units:
                    byte_prev_sent_units=tmp_cal
                    self.progressSignal.emit({'progress_rate':byte_sent/self.file_size,\
                                         'progress_bar_layout':self.progress_bar_layout})
                if not file_data:
                    break

            #check if this thread should stop
            if self.checkStopAndClose()==SELF_STOP:
                return SELF_STOP
            
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

        #receive msg that the file has transferred successfully
        reply_json=self.recvMsgFromServer(5)
        if type(reply_json) is not dict:
            return SOCKET_BROKEN
        
        self.conn_socket.settimeout(prev_timeout)

        if reply_json['content']==FILE_TRANSFER_COMPLETE_MSG:
            return FILE_TRANSFER_COMPLETE
        else:
            return FILE_TRANSFER_FAIL


    def recvMsgFromServer(self,timeout):
        global HEADER_MSG_CONT, HEADER_MSG_END
        global HEADER_SERVER_END, HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global SERVER_STOP, SERVER_RECV_NONE
        global SERVER_RECV_TIMEOUT, SOCKET_BROKEN
        global SELF_STOP
        prev_timeout=self.conn_socket.gettimeout()
        #first receive broadcast message bytestream from client
        #receive header stream
        broadcast_msg=''
        tmp_msg=''
        try:
            tmp_msg=b''
            while len(tmp_msg)<HEADER_LEN:
                tmp_msg+=self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
            tmp_msg= tmp_msg.decode('utf-8')
        except socket.timeout:
            return SERVER_RECV_NONE
        except socket.error as e:
            return SOCKET_BROKEN

        header_content, bytes_num_follow, _= tmp_msg.split('|')
        bytes_num_follow=int(bytes_num_follow)
        
        get_next_msg=False
        if header_content==HEADER_MSG_CONT:
            get_next_msg=True
        #check if server is ended
        if header_content==HEADER_SERVER_END:
            return SERVER_STOP

        try:
            tmp_bytestream=b''
            while len(tmp_bytestream)<bytes_num_follow:
                tmp_bytestream+=self.conn_socket.recv(bytes_num_follow-len(tmp_bytestream))
            broadcast_msg+=tmp_bytestream.decode('utf-8')
        except socket.timeout:
            return SOCKET_BROKEN
        except socket.error as e:
            return SOCKET_BROKEN

        #receive continuing stream if exists
        while get_next_msg:
            tmp_msg=''
            try:
                tmp_msg=b''
                while len(tmp_msg)<HEADER_LEN:
                    tmp_msg+=self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
                tmp_msg= tmp_msg.decode('utf-8')
            except socket.timeout:
                return SOCKET_BROKEN
            except socket.error as e:
                return SOCKET_BROKEN
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
                return SOCKET_BROKEN
            except socket.error as e:
                return SOCKET_BROKEN
                
        self.conn_socket.settimeout(prev_timeout) # prev timeout restore

        #second try to convert received msg to json obj
        broadcast_msg_json={}
        try:
            broadcast_msg_json= json.loads(broadcast_msg)
        except json.JSONDecodeError:
            #just discard received broadcasted bytestream
            return SERVER_RECV_NONE
        return broadcast_msg_json

    def sendMsgToServer(self,msg_byte_stream):
        global MAX_BUFFER_LEN, HEADER_LEN
        global KEY_INCORRECT, SOCKET_BROKEN
        global NAME_UNREGISTERED, CANNOT_MAKE_FILE
        global FILE_TRANSFER_OK, SEND_MSG_OK
        global KEY_INCORRECT_MSG, NAME_UNREGISTERED_MSG
        global CANNOT_MAKE_FILE_MSG, FILE_TRANSFER_OK_MSG
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
        

    def keyAndNameCheck(self,upload=True):
        global MAX_BUFFER_LEN, HEADER_LEN
        global KEY_INCORRECT, SOCKET_BROKEN
        global NAME_UNREGISTERED, CANNOT_MAKE_FILE
        global FILE_TRANSFER_OK
        global KEY_INCORRECT_MSG, NAME_UNREGISTERED_MSG
        global CANNOT_MAKE_FILE_MSG, FILE_TRANSFER_OK_MSG
        byte_stream_index=0
        subtype=None
        if upload:
            subtype='upload'
        else:
            subtype='download'
        msg_byte_stream= makeJSONMSG(['type','login','file_transfer_key',self.file_transfer_key,\
                                      'user_name',self.user_name,'server_thread_id',self.server_thread_id,\
                                      'file_name',os.path.split(self.file_path)[1], \
                                      'subtype',subtype, 'file_id',self.file_id])
        byte_stream_len= len(msg_byte_stream)
        prev_timeout=self.conn_socket.gettimeout() #save previous socket timeout
        self.conn_socket.settimeout(5) # maximum 5 seconds waiting to check password
        reply_json=None
        try:
            while byte_stream_index<byte_stream_len:
                if byte_stream_len-byte_stream_index>MAX_BUFFER_LEN-HEADER_LEN:
                    self.conn_socket.send(makeHeader(HEADER_MSG_CONT,MAX_BUFFER_LEN-HEADER_LEN) + \
                        msg_byte_stream[byte_stream_index:byte_stream_index+(MAX_BUFFER_LEN-HEADER_LEN)])
                else:
                    self.conn_socket.send(makeHeader(HEADER_MSG_END,byte_stream_len-byte_stream_index) + \
                        msg_byte_stream[byte_stream_index:byte_stream_len])
                byte_stream_index+=MAX_BUFFER_LEN-HEADER_LEN
##            reply_json= json.loads(self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8'))
        except socket.timeout:
            return SOCKET_BROKEN
        except socket.error:
            return SOCKET_BROKEN

        reply_json= self.recvMsgFromServer(5)
        if type(reply_json) is not dict:
            return SOCKET_BROKEN
        
        self.conn_socket.settimeout(prev_timeout) # restore previous socket timeout

        if self.file_download:
            self.file_size= reply_json['file_size']

        if reply_json['content']==KEY_INCORRECT_MSG:
            return KEY_INCORRECT
        elif reply_json['content']==NAME_UNREGISTERED_MSG:
            return NAME_UNREGISTERED
        elif reply_json['content']==CANNOT_MAKE_FILE_MSG:
            return CANNOT_MAKE_FILE
        else:
            return FILE_TRANSFER_OK

    def canMakeFileTransferSocket(self):
        global MAKE_SOCKET_ERROR
        #try to open client socket and connect to server
        try:
            conn_socket= socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            conn_socket.settimeout(5) # maximum 5 seconds
            conn_socket.connect((self.ip_addr,self.file_server_port))
            conn_socket.settimeout(None) # turn connection socket to blocking mode
            self.conn_socket= conn_socket
        except socket.timeout as e:
            self.conn_socket=None
            print(e)
            return MAKE_SOCKET_ERROR
        except socket.error as e:
            print(f'cMCS: {self.conn_socket}')
            self.conn_socket=None
            print(e)
            return MAKE_SOCKET_ERROR
        except Exception as e:
            print(e)
            return MAKE_SOCKET_ERROR
        return True  

    def stop(self):
        self.thread_stop=True

    def closeFile(self):
        if self.file is None:
            return
        try:
            self.file.close()
        except:
            pass

    def closeAllSocket(self):
        if self.conn_socket is None:
            return
        try:
            self.conn_socket.close()
        except socket.error as e:
            pass

    def checkStopAndClose(self):
        global SELF_STOP
        if not self.keep_running[0] or self.thread_stop:
            self.closeFile()
            self.closeAllSocket()
            return SELF_STOP
        return False


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
        while self.keep_running[0]:
            time.sleep(0.1)
            if len(self.thread_list)<=0:
                continue
            self.thread_list_mutex.lock()
            current_thread=self.thread_list.pop(0)
            self.thread_list_mutex.unlock()
            current_thread.stop()
            current_thread.wait()

        while len(self.thread_list)>0:
            self.thread_list_mutex.lock()
            current_thread=self.thread_list.pop(0)
            current_thread.stop()
            current_thread.wait()
            self.thread_list_mutex.unlock()

    def appendThread(self,thread):
        self.thread_list_mutex.lock()
        self.thread_list.append(thread)
        self.thread_list_mutex.unlock()

    def stop(self):
        self.keep_running[0]=False

class broadcastMSGListenThread(QThread):
    newMSGSignal= pyqtSignal(dict)
    serverEndSignal= pyqtSignal(dict)
    userStatusSignal= pyqtSignal(dict)
    reconnectedSignal= pyqtSignal(dict)
    def __init__(self,parent,conn_socket,connection_rebuilding,server_address,server_pw_client_name):
        global keep_running, socket_send_mutex
        super().__init__()
        self.parent=parent
        self.conn_socket=conn_socket
        self.connection_rebuilding=connection_rebuilding
        self.server_address=server_address #[0] IP  [1] Port
        self.server_pw_client_name=server_pw_client_name #[0] server pw [1] client name
        self.keep_running=keep_running
        self.thread_stop=False

        #socket send mutex
        self.socket_send_mutex= socket_send_mutex

        self.server_end=False

        #idle count and mutex
        self.idle_count=0
        self.idle_count_max=12
        self.idle_count_mutex=QMutex()

        #reconnection count
        self.reconnection_count=1

    def run(self):
        global HEADER_MSG_CONT, HEADER_MSG_END, HEADER_SERVER_END
        global HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global RECONNECTION_FAIL
        global SERVER_STOP, SERVER_RECV_NONE
        global SERVER_RECV_TIMEOUT, SOCKET_BROKEN
        self.conn_socket.settimeout(0.5) # maximum 0.5 seconds waiting
        while self.keep_running[0] and not self.thread_stop:
            #check if connection rebuilding should happen
            if self.connection_rebuilding[0]:
                #connection rebuilding
                return_val=self.connectionRebuild()
                if return_val==RECONNECTION_FAIL:
                    print('reconnection failed:fatal')
                    break #break or return
                self.connection_rebuilding[0]=False
                print('reconnection return')
                self.resetIdleCount()
                self.reconnectedSignal.emit({}) #inform that reconnection is occurred
                
            broadcast_msg_json=self.recvMsgFromServer(0.5)
            if broadcast_msg_json==SERVER_RECV_NONE or \
               broadcast_msg_json==SERVER_RECV_TIMEOUT or \
               broadcast_msg_json==SOCKET_BROKEN:
                continue
            elif broadcast_msg_json==SERVER_STOP:
                break
            
##            #first receive broadcast message bytestream from client
##            #receive header stream
##            broadcast_msg=''
##            tmp_msg=''
##            try:
##                tmp_msg= self.conn_socket.recv(HEADER_LEN).decode('utf-8')
##            except socket.timeout:
##                #what if the socket was broken what should i do here
##                self.increaseIdleCount() # increase idle count
##                print(f'idle_count: {self.idle_count}')
##                if self.idle_count>=self.idle_count_max:
##                    self.connection_rebuilding[0]=True
##                continue
##            except socket.error as e:
##                #connection rebuilding goes here...
##                self.connection_rebuilding[0]=True
##                print(e)
##                continue
##            self.resetIdleCount() # idle count reset
##            header_content, bytes_num_follow, _= tmp_msg.split('|')
##            bytes_num_follow=int(bytes_num_follow)
##
##            #check if current header is for connection check
##            if header_content==HEADER_CONNECTION_CHECK:
##                try:
##                    self.socket_send_mutex.lock()
##                    self.conn_socket.send(makeHeader(HEADER_CONNECTION_CHECK,0))
##                except socket.error as e:
##                    self.connection_rebuilding[0]=True
##                self.socket_send_mutex.unlock()
##                continue
##            
##            get_next_msg=False
##            if header_content==HEADER_MSG_CONT:
##                get_next_msg=True
##            #check if server is ended
##            if header_content==HEADER_SERVER_END:
##                #do something
##                self.server_end=True
##                self.serverEndSignal.emit({'server_end':True})
##                break
##
####            self.conn_socket.settimeout(3) # maximum 3 seconds waiting
##
##            try:
##                broadcast_msg+=self.conn_socket.recv(bytes_num_follow).decode('utf-8')
##            except socket.timeout:
##                #connection rebuilding goes here
##                pass
##            except socket.error as e:
##                #connection rebuilding goes here
##                self.connection_rebuilding[0]=True
##                continue
##
##            #receive continuing stream if exists
##            while get_next_msg:
##                tmp_msg=''
##                try:
##                    tmp_msg= self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8')
##                except socket.timeout:
##                    #connection rebuilding goes here
##                    pass
##                except socket.error as e:
##                    #connection rebuilding goes here
##                    self.connection_rebuilding[0]=True
##                    continue
##                header_content, bytes_num_follow, _=tmp_msg.split('|')
##                bytes_num_follow=int(bytes_num_follow)
##                if header_content==HEADER_MSG_END:
##                    get_next_msg=False
##
##                try:
##                    broadcast_msg+=self.conn_socket.recv(bytes_num_follow).decode('utf-8')
##                except socket.timeout:
##                    #connection rebuilding goes here
##                    pass
##                except socket.error as e:
##                    #connection rebuilding goes here
##                    self.connection_rebuilding[0]=True
##                    continue
##                
####            self.conn_socket.settimeout(None) # turn connection socket to blocking mode
##
##            #second try to convert received msg to json obj
##            broadcast_msg_json={}
##            try:
##                broadcast_msg_json= json.loads(broadcast_msg)
##            except json.JSONDecodeError:
##                #just discard received broadcasted bytestream
##                continue


            #last, emit received json obj to client chat box window
            if broadcast_msg_json['type']=='broadcast_msg':
                self.newMSGSignal.emit(broadcast_msg_json)
            elif broadcast_msg_json['type']=='user_status_list':
                self.userStatusSignal.emit(broadcast_msg_json)
            elif broadcast_msg_json['type']=='broadcast_file':
                self.newMSGSignal.emit(broadcast_msg_json)

        print('broadcastMSG thread bp')
        if (not self.server_end) and (not self.connection_rebuilding[0]):
            self.sendClientEndMSG()
        self.closeAllSocket()
        print('broadcastMSG thread end')

    def sendClientEndMSG(self):
        global SOCKET_BROKEN
        global HEADER_MSG_CONT, HEADER_MSG_END, HEADER_CLIENT_END
        global MAX_BUFFER_LEN, HEADER_LEN

        self.socket_send_mutex.lock() # mutex for sending into socket
        try:
            self.conn_socket.send(makeHeader(HEADER_CLIENT_END,0))
            print('sCEM after send header')
        except socket.error as e:
            print(e)
            self.socket_send_mutex.unlock() # mutex for sending into socket
            return SOCKET_BROKEN
        self.socket_send_mutex.unlock() # mutex for sending into socket
        print('sCEM bp')
        print('sCEM bp2')
        return True

    def recvMsgFromServer(self,first_timeout):
        global HEADER_MSG_CONT, HEADER_MSG_END
        global HEADER_SERVER_END, HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global SERVER_STOP, SERVER_RECV_NONE
        global SERVER_RECV_TIMEOUT, SOCKET_BROKEN
        prev_timeout=self.conn_socket.gettimeout()
        #first receive broadcast message bytestream from client
        #receive header stream
        broadcast_msg=''
        tmp_msg=''
        try:
            tmp_msg=b''
            while len(tmp_msg)<HEADER_LEN:
                tmp_msg+=self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
            tmp_msg= tmp_msg.decode('utf-8')
        except socket.timeout:
            #what if the socket was broken what should i do here
            self.increaseIdleCount() # increase idle count
            print(f'idle_count: {self.idle_count}')
            if self.idle_count>=self.idle_count_max:
                self.connection_rebuilding[0]=True
            return SERVER_RECV_NONE
        except socket.error as e:
            #connection rebuilding goes here...
            self.connection_rebuilding[0]=True
            print(e)
            return SOCKET_BROKEN
        self.resetIdleCount() # idle count reset
        header_content, bytes_num_follow, _= tmp_msg.split('|')
        bytes_num_follow=int(bytes_num_follow)

        #check if current header is for connection check
        if header_content==HEADER_CONNECTION_CHECK:
            try:
                self.socket_send_mutex.lock()
                self.conn_socket.send(makeHeader(HEADER_CONNECTION_CHECK,0))
            except socket.error as e:
                self.connection_rebuilding[0]=True
            self.socket_send_mutex.unlock()
            return SERVER_RECV_NONE
        
        get_next_msg=False
        if header_content==HEADER_MSG_CONT:
            get_next_msg=True
        #check if server is ended
        if header_content==HEADER_SERVER_END:
            #do something
            self.server_end=True
            self.serverEndSignal.emit({'server_end':True})
            return SERVER_STOP

##            self.conn_socket.settimeout(3) # maximum 3 seconds waiting

        try:
            tmp_bytestream=b''
            while len(tmp_bytestream)<bytes_num_follow:
                tmp_bytestream+=self.conn_socket.recv(bytes_num_follow-len(tmp_bytestream))
            broadcast_msg+=tmp_bytestream.decode('utf-8')
        except socket.timeout:
            #connection rebuilding goes here
            self.connection_rebuilding[0]=True
            return SOCKET_BROKEN
        except socket.error as e:
            #connection rebuilding goes here
            self.connection_rebuilding[0]=True
            return SOCKET_BROKEN

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
                self.connection_rebuilding[0]=True
                return SOCKET_BROKEN
            except socket.error as e:
                #connection rebuilding goes here
                self.connection_rebuilding[0]=True
                return SOCKET_BROKEN
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
                self.connection_rebuilding[0]=True
                return SOCKET_BROKEN
            except socket.error as e:
                #connection rebuilding goes here
                self.connection_rebuilding[0]=True
                return SOCKET_BROKEN
                
        self.conn_socket.settimeout(prev_timeout) # prev timeout restore

        #second try to convert received msg to json obj
        broadcast_msg_json={}
        try:
            broadcast_msg_json= json.loads(broadcast_msg)
        except json.JSONDecodeError:
            #just discard received broadcasted bytestream
            return SERVER_RECV_NONE
        return broadcast_msg_json

    def closeAllSocket(self):
        try:
            if self.conn_socket.fileno()>=0:
                self.conn_socket.close()
        except socket.error as e:
            print('broadcastMSG thread bp0')
            pass
        except Exception as e:
            print(e)
        print('broadcastMSG thread bp')

    def connectionRebuild(self):
        global PW_INCORRECT, ILLEGAL_RECONNECTION
        global SOCKET_BROKEN, RECONNECTION_FAIL
        time.sleep(3)

        print('connection rebuilding start')

        #first try to close remaining socket
        prev_timeout=self.conn_socket.gettimeout() #save timeout time of prev socket
        self.closeAllSocket()
        self.conn_socket=None

        #then try to rebuild connection with server
        while self.keep_running[0] and not self.thread_stop:
            time.sleep(0.5)
            if self.conn_socket is None:
                self.conn_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            print('cR bp')
            #connect to server
            try:
                self.conn_socket.connect(self.server_address)
            except socket.error:
                continue
            except Exception:
                continue

            print('cR bp2')

            #password and name check
            return_val= self.passwordAndNameCheck()
            if return_val==PW_INCORRECT or return_val==ILLEGAL_RECONNECTION:
                return RECONNECTION_FAIL
            elif return_val==SOCKET_BROKEN:
                self.conn_socket=None
                continue

            print('connection rebuilding success')

            #end rebuilding process
            self.reconnection_count+=1 #reconnection count update
            self.conn_socket.settimeout(prev_timeout) #restore timeout time
            self.parent.changeConnectionSocket(self.conn_socket)
            self.connection_rebuilding[0]=False
            return True
        

    def passwordAndNameCheck(self):
        global MAX_BUFFER_LEN, HEADER_LEN
        global PW_INCORRECT, SOCKET_BROKEN
        global NAME_DUPLICATED, LOGIN_OK
        global ILLEGAL_RECONNECTION
        global PW_CORRECT_MSG, PW_INCORRECT_MSG
        global NAME_OK_MSG, NAME_DUPLICATED_MSG
        global LOGIN_OK_MSG, ILLEGAL_RECONNECTION_MSG
        pw=self.server_pw_client_name[0]
        name=self.server_pw_client_name[1]
        
        byte_stream_index=0
        msg_byte_stream= makeJSONMSG(['type','login','pw',pw,'name',name,\
                                               'reconnection_count',self.reconnection_count])
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
##            reply_json= json.loads(self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8'))
        except socket.timeout:
            return SOCKET_BROKEN
        except socket.error:
            return SOCKET_BROKEN

        reply_json=self.recvMsgFromServer(5)
        if type(reply_json) is not dict:
            return SOCKET_BROKEN
        
        self.conn_socket.settimeout(prev_timeout) # turn connection socket to blocking mode

        if reply_json['content']==PW_INCORRECT_MSG:
            return PW_INCORRECT
        elif reply_json['content']==ILLEGAL_RECONNECTION_MSG:
            return ILLEGAL_RECONNECTION
        else:
            return LOGIN_OK

    def increaseIdleCount(self):
        self.idle_count_mutex.lock()
        self.idle_count+=1
        self.idle_count_mutex.unlock()

    def resetIdleCount(self):
        self.idle_count_mutex.lock()
        self.idle_count=0
        self.idle_count_mutex.unlock()
       
    def stop(self):
        self.thread_stop=True

class dialogWindow(QDialog, dialog_form_class):
    def __init__(self,msg,wait_to_close=False):
        super().__init__()
        self.setupUi(self)
        self.setFixedSize(self.size())
        self.label.clear()
        self.label.setText(msg)
        self.label.setAlignment(Qt.AlignCenter)
        self.okButton.clicked.connect(lambda: self.close())

        self.wait_to_close= wait_to_close

    def closeEvent(self,event):
        if not self.wait_to_close:
            super(dialogWindow,self).closeEvent(event)
        else:
            event.ignore()

    def setClose(self,wait_to_close):
        self.wait_to_close= wait_to_close

    def dialogClose(self):
        self.close()

##class connWindow(QDialog, conn_form_class):
##    def __init__(self):
##        super().__init__()
##        self.setupUi(self)
##        self.label.clear()
##        self.label.setText('logging in to the server...')
##        self.label.setAlignment(Qt.AlignCenter)
##
##    def closeEvent(self,event):
##        event.ignore()
        

##class connectWindow(QDialog, dialog_form_class):
##    def __init__(self):
##        super().__init__()
##        self.setupUi(self)
##        self.label.clear()
##        self.label.setText('logging in to the server...')
##        self.label.setAlignment(Qt.AlignCenter)
##        self.okButton.hide()
##
##        self.close_enabled=False
##
##    def closeEvent(self,event):
##        if self.close_enabled:
##            super(connectWindow,self).closeEvent(event)
##        else:
##            event.ignore()
        

class loginWindow(QMainWindow, login_form_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.setFixedSize(self.size())
        self.setWindowTitle('chat login window')
        self.resize(self.size().width(),210)
        self.loginButton.clicked.connect(self.login)
        self.cancelButton.clicked.connect(self.cancel)
##        self.setCloseButton.clicked.connect(self.setCloseFunc)
        self.serverIP=''
        self.serverPort=None
        self.pw=''
        self.name=''
        self.conn_socket=None

        self.close_enabled=True
        self.open_chat_window=False

##        self.toggleButton.clicked.connect(self.toggleWindow)
##        self.conn_window=connWindow()

##        self.do_show_handle=True

##        self.setClose=False

        #file transfer server port and key
        self.file_server_port=None
        self.file_transfer_key=None
        self.server_thread_id=None

    def closeEvent(self, event):
        if self.close_enabled:
            super(loginWindow,self).closeEvent(event)
        else:
            event.ignore()
##
##    def setCloseFunc(self):
##        self.setClose=True
##    def showEvent(self,event):
##        if self.do_show_handle:
##            dlg=dialogWindow('show execution test')
##            dlg.exec()
##        self.do_show_handle=False
##        event.accept()

    def toggleWindow(self):
        if self.conn_window.isVisible():
            self.conn_window.hide()
        else:
            self.conn_window.show()

    def login(self):
        global PORT_NUM_ERROR, MAKE_SOCKET_ERROR, PW_INVALID
        global PW_INCORRECT, NAME_INVALID, NAME_DUPLICATED, SOCKET_BROKEN
        global password_regex, name_regex
        self.DisableAllButton() #set all button disabled
        
        self.serverIP=self.serverIPEdit.text()
        self.serverPort=self.serverPortEdit.text()
        self.pw=self.pwEdit.text()
        self.name=self.nameEdit.text()
        print(f'serverIP: {self.serverIP}')
        print(f'serverPort: {self.serverPort}')
        print(f'pw: {self.pw}')
        print(f'name: {self.name}')

        #first check if password is valid
        if not password_regex.match(self.pw):
            self.showDialog('login process failed\n:invalid password\n:alphabet, digit, !,@,#,%,& and * are allowed\n:empty password is not allowed')
            self.EnableAllButton() #set all button enabled
            return

        #second check if name is valid
        if not name_regex.match(self.name):
            self.showDialog('login process failed\n:invalid name\n:alphabet, digit, and \'_\' are allowed\n:empty name is not allowed')
            self.EnableAllButton() #set all button enabled
            return

        #third make client socket
        return_val= self.canMakeClientSocket()
        if return_val==1:
            pass
        elif return_val==PORT_NUM_ERROR:
            self.showDialog('login process failed\n:invalid port number')
            self.EnableAllButton() #set all button enabled
            return
        else:
            self.showDialog('login process failed\n:invalid IP address or connection failure')
            self.EnableAllButton() #set all button enabled
            return

##        #fourth check if password is correct
##        return_val= self.passwordCorrectCheck()
##        if return_val==PW_INCORRECT:
##            self.showDialog('login process failed\n:password incorrect')
##            self.EnableAllButton() #set all button enabled
##            self.closeAllSocket() #close client socket
##            return
##        elif return_val==SOCKET_BROKEN:
##            self.showDialog('login process failed\n:server not responding')
##            self.EnableAllButton() #set all button enabled
##            self.closeAllSocket() #close client socket
##            return
##
##        #last check if name is already registered in server
##        return_val= self.nameDuplicatedCheck()
##        if return_val==NAME_DUPLICATED:
##            self.showDialog('login process failed\n:name already registered on server')
##            self.EnableAllButton() #set all button enabled
##            self.closeAllSocket() #close client socket
##            return
##        elif return_val==SOCKET_BROKEN:
##            self.showDialog('login process failed\n:server not responding')
##            self.EnableAllButton() #set all button enabled
##            self.closeAllSocket() #close client socket
##            return

        #last check if password is correct and name is already registered in server
        return_val= self.passwordAndNameCheck()
        if return_val==PW_INCORRECT:
            self.showDialog('login process failed\n:password incorrect')
            self.EnableAllButton() #set all button enabled
            self.closeAllSocket() #close client socket
            return
        elif return_val==NAME_DUPLICATED:
            self.showDialog('login process failed\n:name already registered on server')
            self.EnableAllButton() #set all button enabled
            self.closeAllSocket() #close client socket
            return
        elif return_val==SOCKET_BROKEN:
            self.showDialog('login process failed\n:server not responding')
            self.EnableAllButton() #set all button enabled
            self.closeAllSocket() #close client socket
            return

        self.EnableAllButton() #set all button enabled

        #if login process were successful, close this login window
        self.open_chat_window=True
        self.close()
        

    def cancel(self):
        self.close()

    def canMakeClientSocket(self):
        global PORT_NUM_ERROR, MAKE_SOCKET_ERROR
        #check if given port is valid int
        try:
            self.serverPort= int(self.serverPort)
        except Exception:
            return PORT_NUM_ERROR
        #try to open client socket and connect to server
        try:
            conn_socket= socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            conn_socket.settimeout(5) # maximum 5 seconds waiting to check password
            conn_socket.connect((self.serverIP,self.serverPort))
            conn_socket.settimeout(None) # turn connection socket to blocking mode
            self.conn_socket= conn_socket
        except socket.timeout as e:
            self.conn_socket=None
            print(e)
            return MAKE_SOCKET_ERROR
        except socket.error as e:
            print(f'cMCS: {self.conn_socket}')
            self.conn_socket=None
            print(e)
            return MAKE_SOCKET_ERROR
        except Exception as e:
            print(e)
        return True

    def passwordCorrectCheck(self):
        global PW_INCORRECT, SOCKET_BROKEN
        global PW_CORRECT_MSG, PW_INCORRECT_MSG
        prev_timeout=self.conn_socket.gettimeout()
        self.conn_socket.settimeout(3) # maximum 3 seconds waiting to check password
        try:
            self.conn_socket.send(makeJSONMSG(['type','login','content',self.pw]))
            reply_json= json.loads(self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8'))
        except socket.timeout:
            return SOCKET_BROKEN
        except socket.error:
            return SOCKET_BROKEN
        self.conn_socket.settimeout(prev_timeout) # restore timeout

        if reply_json['content']==PW_CORRECT_MSG:
            return True
        else:
            return PW_INCORRECT

    def nameDuplicatedCheck(self):
        global NAME_DUPLICATED, SOCKET_BROKEN
        global NAME_OK_MSG, NAME_DUPLICATED_MSG
        self.conn_socket.settimeout(5) # maximum 3 seconds waiting to check password
        try:
            self.conn_socket.send(makeJSONMSG(['type','login','content',self.name]))
            reply_json= json.loads(self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8'))
        except socket.timeout:
            return SOCKET_BROKEN
        except socket.error:
            return SOCKET_BROKEN
        self.conn_socket.settimeout(None) # turn connection socket to blocking mode

        if reply_json['content']==NAME_OK_MSG:
            return True
        else:
            return NAME_DUPLICATED

    def passwordAndNameCheck(self):
        global MAX_BUFFER_LEN, HEADER_LEN
        global PW_INCORRECT, SOCKET_BROKEN
        global NAME_DUPLICATED, LOGIN_OK
        global PW_CORRECT_MSG, PW_INCORRECT_MSG
        global NAME_OK_MSG, NAME_DUPLICATED_MSG
        global LOGIN_OK_MSG
        byte_stream_index=0
        msg_byte_stream= makeJSONMSG(['type','login','pw',self.pw,'name',self.name,\
                                               'reconnection_count',0])
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
##            reply_json= json.loads(self.conn_socket.recv(MAX_BUFFER_LEN).decode('utf-8'))
        except socket.timeout:
            return SOCKET_BROKEN
        except socket.error:
            return SOCKET_BROKEN

        reply_json=self.recvMsgFromServer(5)
        
        self.conn_socket.settimeout(prev_timeout) # restore timeout

        if type(reply_json) is not dict:
            return SOCKET_BROKEN

        if reply_json['content']==PW_INCORRECT_MSG:
            return PW_INCORRECT
        elif reply_json['content']==NAME_DUPLICATED_MSG:
            return NAME_DUPLICATED
        else:
            self.file_server_port=reply_json['file_server_port']
            self.file_transfer_key=reply_json['file_transfer_key']
            self.server_thread_id=reply_json['thread_id']
            return LOGIN_OK

    def recvMsgFromServer(self,timeout):
        global HEADER_MSG_CONT, HEADER_MSG_END
        global HEADER_SERVER_END, HEADER_CONNECTION_CHECK
        global MAX_BUFFER_LEN, HEADER_LEN
        global SERVER_STOP, SERVER_RECV_NONE
        global SERVER_RECV_TIMEOUT, SOCKET_BROKEN
        global SELF_STOP
        prev_timeout=self.conn_socket.gettimeout()
        #first receive broadcast message bytestream from client
        #receive header stream
        broadcast_msg=''
        tmp_msg=''
        try:
            tmp_msg=b''
            while len(tmp_msg)<HEADER_LEN:
                tmp_msg+=self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
            tmp_msg= tmp_msg.decode('utf-8')
        except socket.timeout:
            return SERVER_RECV_NONE
        except socket.error as e:
            return SOCKET_BROKEN

        header_content, bytes_num_follow, _= tmp_msg.split('|')
        bytes_num_follow=int(bytes_num_follow)
        
        get_next_msg=False
        if header_content==HEADER_MSG_CONT:
            get_next_msg=True

        try:
            tmp_bytestream=b''
            while len(tmp_bytestream)<bytes_num_follow:
                tmp_bytestream+=self.conn_socket.recv(bytes_num_follow-len(tmp_bytestream))
            broadcast_msg+=tmp_bytestream.decode('utf-8')
        except socket.timeout:
            return SOCKET_BROKEN
        except socket.error as e:
            return SOCKET_BROKEN

        #receive continuing stream if exists
        while get_next_msg:
            tmp_msg=''
            try:
                tmp_msg=b''
                while len(tmp_msg)<HEADER_LEN:
                    tmp_msg+=self.conn_socket.recv(HEADER_LEN-len(tmp_msg))
                tmp_msg= tmp_msg.decode('utf-8')
            except socket.timeout:
                return SOCKET_BROKEN
            except socket.error as e:
                return SOCKET_BROKEN
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
                return SOCKET_BROKEN
            except socket.error as e:
                return SOCKET_BROKEN
                
        self.conn_socket.settimeout(prev_timeout) # prev timeout restore

        #second try to convert received msg to json obj
        broadcast_msg_json={}
        try:
            broadcast_msg_json= json.loads(broadcast_msg)
        except json.JSONDecodeError:
            #just discard received broadcasted bytestream
            return SERVER_RECV_NONE
        return broadcast_msg_json

    def EnableAllButton(self):
        self.loginButton.setEnabled(True)
        self.cancelButton.setEnabled(True)
        self.close_enabled=True
    def DisableAllButton(self):
        self.close_enabled=False
        self.loginButton.setDisabled(True)
        self.cancelButton.setDisabled(True)
    def showDialog(self,msg):
        dlg=dialogWindow(msg)
        dlg.setWindowTitle('client dialog')
        dlg.exec()

    def closeAllSocket(self):
        try:
            if self.conn_socket.fileno()>=0:
                self.conn_socket.close()
        except socket.error as e:
            pass
        self.conn_socket=None

# class for restoring some widgets related to displaying users' status
class userStatus():
    def __init__(self,name,container_widget, image_label):
        self.name=name
        self.container_widget=container_widget
        self.image_label=image_label

    def getName(self):
        return self.name

    def getContainerWidget(self):
        return self.container_widget

    def setConnected(self):
        self.image_label.setPixmap(QPixmap("default_user.png"))

    def setDisconnected(self):
        self.image_label.setPixmap(QPixmap("disconnected_user.png"))

class chatBoxWindow(QMainWindow, chat_form_class):
    def __init__(self, conn_socket, server_address, server_pw_client_name, file_server_port_and_key,\
                 server_thread_id):
        global socket_send_mutex, keep_running
        super().__init__()
        self.setupUi(self)
        self.setFixedSize(self.size())
        self.pushButton.clicked.connect(self.send)
        self.fileButton.clicked.connect(self.fileTransfer)
        self.lineEdit.returnPressed.connect(self.send)
        ###########################
        # chat message scroll area(vertical)
        ###########################
        self.scrollArea.setAutoFillBackground(True)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setWidgetResizable(True)
##        self.scrollArea.setAlignment(Qt.AlignLeft)
        self.scrollArea.setAlignment(Qt.AlignTop)

##        self.scroll_layout= QVBoxLayout()
        self.scroll_layout= QVBoxLayout()
        self.scroll_layout.setContentsMargins(0,0,0,0)
        self.scroll_layout.setSpacing(20)
##        self.scrollArea.setLayout(self.scroll_layout)
        self.scroll_layout.setAlignment(Qt.AlignTop)

        self.scroll_widget=QWidget()
        self.scroll_widget.setStyleSheet("""
            padding: 0px;
        """)
        self.scroll_widget.setLayout(self.scroll_layout)
        self.scroll_widget.installEventFilter(self)

        self.scrollArea.setWidget(self.scroll_widget)

        self.scroll_vbar=self.scrollArea.verticalScrollBar()

        #mutex for updating main widget(chat box)
        self.chat_box_mutex= QMutex()

        ###########################
        #user status scroll area(horizontal)
        ###########################
        self.user_status_scrollArea.setAutoFillBackground(True)
        self.user_status_scrollArea.setStyleSheet("""
            border:0px;
        """)
        self.user_status_scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
##        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.user_status_scrollArea.setWidgetResizable(True)
##        self.scrollArea.setAlignment(Qt.AlignLeft)
        self.user_status_scrollArea.setAlignment(Qt.AlignLeft)

##        self.scroll_layout= QVBoxLayout()
        self.user_status_scroll_layout= QHBoxLayout()
        self.user_status_scroll_layout.setContentsMargins(0,0,0,0)
        self.user_status_scroll_layout.setSpacing(0)
##        self.scrollArea.setLayout(self.scroll_layout)
        self.user_status_scroll_layout.setAlignment(Qt.AlignLeft)

        self.user_status_scroll_widget=QWidget()
        self.user_status_scroll_widget.setStyleSheet("""
            padding: 0px;
        """)
        self.user_status_scroll_widget.setLayout(self.user_status_scroll_layout)
        self.user_status_scroll_widget.installEventFilter(self)

        self.user_status_scrollArea.setWidget(self.user_status_scroll_widget)

        self.user_status_scroll_hbar=self.scrollArea.horizontalScrollBar()
        self.user_status_scroll_hbar_height=QApplication.style().pixelMetric(QStyle.PM_ScrollBarExtent)
        print(f'scroll bar width(height): {self.user_status_scroll_hbar_height}')

        #mutex for updating user status scroll area
        self.user_status_scrollArea_mutex=QMutex()

        #keep running flag reset
        self.keep_running=keep_running
        self.keep_running[0]=True

        #user list and mutex
        self.user_list=[]
        self.user_list_mutex=QMutex()

        #set conn_socket
        self.conn_socket= conn_socket

        #server address [0] IP, [1] Port
        self.server_address=server_address

        #[0] server pw, [1] client name
        self.server_pw_client_name=server_pw_client_name

        #[0] file server port, [1] file transfer key
        self.file_server_port_and_key=file_server_port_and_key
        print(f' file server port and key: {self.file_server_port_and_key}')

        #server thread id
        self.server_thread_id=server_thread_id

        #mutex for socket sending
        self.socket_send_mutex= socket_send_mutex

        

        #print font
        print(f'current font:{self.font().family()}')

        #connection rebuilding flag
        self.connection_rebuilding=[False]

        #broadcast message listening thread
        self.broadcast_msg_listen_thread=broadcastMSGListenThread(self,self.conn_socket,self.connection_rebuilding,\
                                                                  self.server_address, self.server_pw_client_name)
        self.broadcast_msg_listen_thread.newMSGSignal.connect(self.displayBroadcastMSG)
        self.broadcast_msg_listen_thread.serverEndSignal.connect(self.handleServerEnd)
        self.broadcast_msg_listen_thread.userStatusSignal.connect(self.handleUserStatus)
        self.broadcast_msg_listen_thread.reconnectedSignal.connect(self.handleReconnected)
        self.broadcast_msg_listen_thread.start()

        #client thread collector thread
        self.file_thread_collector_thread=threadCollectWorker(self)
        self.file_thread_collector_thread.start()

        #temporary client thread reservoir
        self.tmp_file_thread_list=[]
        self.tmp_file_thread_list_max_len=100
        self.tmp_file_thread_list_mutex=QMutex()


    def closeEvent(self,event):
        global keep_running
        #socket closing goes here
        print('cE bp0')
##        self.sendClientEndMSG()

        print('cE bp')
        keep_running[0]=False
        #stop msg broadcast thread
        self.broadcast_msg_listen_thread.stop()
        self.broadcast_msg_listen_thread.wait()

        #stop and delete file threads waiting in tmp list
        self.tmp_file_thread_list_mutex.lock()
        while len(self.tmp_file_thread_list)>0:
            time.sleep(0.1)
        self.tmp_file_thread_list_mutex.unlock()
        
        #also stop and wait file thread collector thread
        #this process should be in correct order
        self.file_thread_collector_thread.stop()
        self.file_thread_collector_thread.wait()
        
        super(chatBoxWindow,self).closeEvent(event)

    def sendClientEndMSG(self):
        global SOCKET_BROKEN
        global HEADER_MSG_CONT, HEADER_MSG_END, HEADER_CLIENT_END
        global MAX_BUFFER_LEN, HEADER_LEN

        self.socket_send_mutex.lock() # mutex for sending into socket
        try:
            self.conn_socket.send(makeHeader(HEADER_CLIENT_END,0))
            print('sCEM after send header')
        except socket.error as e:
            print(e)
            self.socket_send_mutex.unlock() # mutex for sending into socket
##            return SOCKET_BROKEN
        self.socket_send_mutex.unlock() # mutex for sending into socket
##        print('sCEM bp')
        print('sCEM bp2')
##        return True
            

    def eventFilter(self,source,event):
        if source is self.scroll_widget and event.type() == QEvent.Resize:
            self.scroll_vbar.setValue(self.scroll_vbar.maximum())
        return super().eventFilter(source,event)

    def send(self):
##        global chat_count, name_list
        global MSG_BOX_PAD_VERT, MSG_BOX_PAD_HORZ, MSG_ADDITIONAL_SPACE
        global WIDGET_PAD_VERT
        
        msg=self.lineEdit.text()        
        if len(msg)==0:
            return
        else:
            self.lineEdit.setText('')

        self.displayMSGToWidget(msg)

        size=self.scroll_widget.size()
##        print(f'widget width: {size.width()}, widget height: {widget.height()}')

        size=self.scrollArea.size()
        print(f'sa width: {size.width()}, sa height: {size.height()}')


        # broadcast my message
        if not self.connection_rebuilding[0]:
            return_val= self.broadcastMessage(msg)
            if return_val==1:
                self.broadcast_msg_listen_thread.resetIdleCount() # reset idle count of broadcast thread
            else:
                #connection rebuilding goes here
                self.connection_rebuilding[0]=True
                self.closeAllSocket()
                pass

    def broadcastMessage(self,msg):
        global SOCKET_BROKEN
        global HEADER_MSG_CONT, HEADER_MSG_END
        global MAX_BUFFER_LEN, HEADER_LEN

        byte_stream_index=0
        msg_byte_stream= makeJSONMSG(['type','broadcast_msg','content',msg])
        byte_stream_len= len(msg_byte_stream)

        self.socket_send_mutex.lock() # mutex for sending into socket
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
            print(e)
            self.socket_send_mutex.unlock() # mutex for sending into socket
            return SOCKET_BROKEN
        self.socket_send_mutex.unlock() # mutex for sending into socket
        return True

    def displayBroadcastMSG(self,broadcast_msg_data):
        if broadcast_msg_data['type']=='broadcast_msg':
            self.displayMSGToWidget(broadcast_msg_data['content'],broadcast_msg_data['from_name'])
        elif broadcast_msg_data['type']=='broadcast_file':
            self.displayMSGToWidget(broadcast_msg_data['content'],broadcast_msg_data['from_name'], \
                                    True,False,broadcast_msg_data)

    def displayMSGToWidget(self,msg,from_name='',file_download=False, file_upload=False,file_data=None):
        global MSG_BOX_PAD_VERT, MSG_BOX_PAD_HORZ, MSG_ADDITIONAL_SPACE
        global WIDGET_PAD_VERT
            
        metrics= QFontMetrics(self.font())
        msg_box_max_width= self.scroll_widget.size().width()//2
        font_height= metrics.height()

        download_button_min_width=metrics.boundingRect('download').width()+4
        
        sentences=msg.split('\n')
        msg_box_width,line_count=0,0
        for sentence in sentences:
            sentence_width= metrics.boundingRect(sentence).width() + MSG_ADDITIONAL_SPACE
            msg_box_width=min(msg_box_max_width,max(msg_box_width, sentence_width))
            line_count+=sentence_width // msg_box_max_width
            if sentence_width%msg_box_max_width>0:
                line_count+=1

        textBrowser_width= msg_box_width + 15
        if file_download:
            textBrowser_width= max(textBrowser_width,download_button_min_width)
        textBrowser_height= line_count*(font_height+1)+MSG_BOX_PAD_VERT*2


        width,height=0,0

        label=None
        label_layout=None
        if from_name!='':
            label=QLabel(from_name)
            label.setStyleSheet("""
                padding:0px;
                margin:0px;
            """)
            label_layout= QHBoxLayout()
            label_layout.addWidget(label)
            height+=font_height

        textBrowser= QTextBrowser()
        textBrowser.setText(msg)
        if from_name=='':
            textBrowser.setStyleSheet("""
                border: 3px solid yellow;
                padding: 0px;
                margin-left: 0px;
                margin-right: 0px;
                margin-top: 0px;
                margin-bottom: 0px;
            """)
        else:
            textBrowser.setStyleSheet("""
                border: 3px solid gray;
                padding: 0px;
                margin-left: 0px;
                margin-right: 0px;
                margin-top: 0px;
                margin-bottom: 0px;
            """)


        textBrowser.setMinimumSize(textBrowser_width,textBrowser_height)
        textBrowser.setMaximumSize(textBrowser_width,textBrowser_height)
        textBrowser.resize(textBrowser_width,textBrowser_height)
        textBrowser_layout= QHBoxLayout()
        textBrowser_layout.addWidget(textBrowser)

        width+=textBrowser.frameGeometry().width()
        height+=textBrowser.frameGeometry().height()+2

        button=None
        button_layout=None
        if file_download:
            button= QPushButton()
            button.setText('download')
            button.setStyleSheet("""
                margin-left: 0px;
                margin-right: 0px;
                margin-top: 0px;
                margin-bottom: 0px;
            """)

            button_height= font_height+MSG_BOX_PAD_VERT*2
            button.setMinimumSize(textBrowser_width,button_height)
            button.setMaximumSize(textBrowser_width,button_height)
            button.resize(textBrowser_width,button_height)

            button_layout= QHBoxLayout()
            button_layout.addWidget(button)
            height+=button.frameGeometry().height()

        progressBar=None
        progressBar_layout=None
        if file_download or file_upload:
            progressBar= QProgressBar()
            progressBar.setValue(0)
            progressBar_height= font_height+MSG_BOX_PAD_VERT*2
            progressBar_min_width= 250
            progressBar_width= max(progressBar_min_width,textBrowser_width)
            progressBar.setMinimumSize(progressBar_width,progressBar_height)
            progressBar.setMaximumSize(progressBar_width,progressBar_height)
            progressBar.resize(progressBar_width,progressBar_height)
            progressBar.setStyleSheet("""
                margin-left: 0px;
                margin-right: 0px;
                margin-top: 0px;
                margin-bottom: 0px;
            """)
            width=max(width,progressBar_width)
            height+=progressBar.frameGeometry().height()+2

            if file_download:
                progressBar.hide()

            progressBar_layout= QHBoxLayout()
            progressBar_layout.addWidget(progressBar)

        layout= QVBoxLayout()

        if from_name!='':
            layout.addLayout(label_layout)
##            layout.addWidget(label)
##            layout.setAlignment(Qt.AlignLeft)
        else:
            pass
##            layout.setAlignment(Qt.AlignRight)
        
        layout.addLayout(textBrowser_layout)
            
##        layout.addWidget(textBrowser)
        if file_download:
            layout.addLayout(button_layout)
##            layout.addWidget(button)
        if file_download or file_upload:
            layout.addLayout(progressBar_layout)
##        layout.addWidget(progressBar)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)


        layout.setAlignment(Qt.AlignTop)
        if from_name!='':
            label_layout.setAlignment(Qt.AlignLeft)
            textBrowser_layout.setAlignment(Qt.AlignLeft)
            if file_download:
                button_layout.setAlignment(Qt.AlignLeft)
            if file_download or file_upload:
                progressBar_layout.setAlignment(Qt.AlignLeft)
        else:
            textBrowser_layout.setAlignment(Qt.AlignRight)
            if file_download:
                button_layout.setAlignment(Qt.AlignRight)
            if file_download or file_upload:
                progressBar_layout.setAlignment(Qt.AlignRight)



        layout.setSizeConstraint(QLayout.SetNoConstraint)

        widget= QWidget()
        widget.setLayout(layout)
        widget.setStyleSheet("""
            padding: 0px;
            margin: 0px;
        """)

        widget.setMinimumSize(widget.minimumSize().width(),height)
        widget.setMaximumSize(widget.maximumSize().width(),height)
        widget.resize(widget.size().width(),height)
        widget.setLayout(layout)

        self.chat_box_mutex.lock() # chat box mutex
##        self.scroll_layout.addLayout(layout)
        self.scroll_layout.addWidget(widget)
        self.chat_box_mutex.unlock() # chat box mutex

        #progress bar handling
        if file_upload:
            return (layout,progressBar_layout)
        if file_download:
            button.clicked.connect(lambda: self.fileReceive(button,layout,progressBar_layout,msg,from_name, \
                                                            file_data['file_id']))

    def removeOtherUser(self,name):
        target_widget=None
        self.user_list_mutex.lock()
        for i in range(len(self.user_list)):
            entry=self.user_list[i]
            if entry.getName()==name:
                self.user_list.pop(i)
                target_widget=entry.getContainerWidget()
                break
        self.user_list_mutex.unlock()

        if target_widget is None:
            return

        self.user_status_scrollArea_mutex.lock()
        target_widget.deleteLater()
        self.user_status_scrollArea_mutex.unlock()

    def displayUserStatusChange(self,name,connected):
        self.user_list_mutex.lock()
        for entry in self.user_list:
            if entry.getName()==name:
                if connected:
                    entry.setConnected()
                else:
                    entry.setDisconnected()
                break
        self.user_list_mutex.unlock()

    def displayUserStatusToWidget(self,name,connected):
        user_status_box_max_height=self.user_status_scroll_widget.size().height()-self.user_status_scroll_hbar_height
        user_status_box_max_width= 54

        width,height=56,0

        # user status image
        image_side_len=40
        status_image=QLabel()
        status_image.setStyleSheet("""
            padding: 0px;
            margin: 0px;
        """)
        status_image.setAlignment(Qt.AlignCenter)
        if connected:
            status_image.setPixmap(QPixmap("default_user.png"))
        else:
            status_image.setPixmap(QPixmap("disconnected_user.png"))
        status_image.setScaledContents(True)
        status_image.setMinimumSize(image_side_len,image_side_len)
        status_image.setMaximumSize(image_side_len,image_side_len)
        status_image.resize(image_side_len,image_side_len)


        inner_layout=QHBoxLayout()
        inner_layout.addWidget(status_image)
        inner_layout.setAlignment(Qt.AlignCenter)
       

        height+=image_side_len

        # user name tag
        
        label_font_size=6 # set font size of label(user name)
        label_font=QFont(self.font().family(),label_font_size)
        metrics= QFontMetrics(label_font)
        #calculate maximum characters that can be displayed on status box
        display_name=''
        full_name_displayed=True
        for i in range(len(name)):
            if metrics.boundingRect(display_name+name[i]).width()<=user_status_box_max_width:
                display_name+=name[i]
            else:
                full_name_displayed=False
                break
        if not full_name_displayed:
            display_name+='\n...'
        label_height= metrics.height()*2
        label=QLabel(display_name)
        label.setAlignment(Qt.AlignCenter)
        label.setFont(label_font)
        label.setMinimumSize(width,label_height)
        label.setMaximumSize(width,label_height)
        label.resize(width,label_height)
        label.setStyleSheet("""
            padding:0px;
            margin:0px;
        """)
        height+=label_height

        layout= QVBoxLayout()
        
        
        layout.addLayout(inner_layout)
        layout.addWidget(label)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)

        layout.setSizeConstraint(QLayout.SetNoConstraint)
        

        widget= QWidget()
        widget.setLayout(layout)
        widget.setStyleSheet("""
            padding: 0px;
            margin: 0px;
        """)

        widget.setMinimumSize(widget.minimumSize().width(),height)
        widget.setMaximumSize(widget.maximumSize().width(),height)
        widget.resize(widget.size().width(),height)

        #display user status
        self.user_list_mutex.lock()
        self.user_list.append(userStatus(name,widget,status_image))
        self.user_list_mutex.unlock()

        #save widget
        self.user_status_scrollArea_mutex.lock()
        self.user_status_scroll_layout.addWidget(widget)
        self.user_status_scrollArea_mutex.unlock()
        
    def handleServerEnd(self,server_end_data):
        if server_end_data['server_end']==True:
            self.showDialog('server ended, exiting chat window')#show dialog
            self.close()
        else:
            pass

    def handleUserStatus(self,user_status_data):
        if user_status_data['option']=='new':
            if user_status_data['content'] is None:
                #when other client is entering
                self.displayUserStatusToWidget(user_status_data['from_name'],True)
            else:
                #when this client is entering(retreive other clients already exist)
                for name, status in user_status_data['content']:
                    self.displayUserStatusToWidget(name,status)
        elif user_status_data['option']=='out':
            self.removeOtherUser(user_status_data['from_name'])
        elif user_status_data['option']=='change':
            self.displayUserStatusChange(user_status_data['from_name'],user_status_data['connected'])

    def handleReconnected(self,reconnected_data):
        #clear user list array
        self.user_list_mutex.lock()
        self.user_list=[]
        self.user_list_mutex.unlock()

        #clear scroll area widget
        self.user_status_scrollArea_mutex.lock()
        for i in range(self.user_status_scroll_layout.count()-1,-1,-1):
            self.user_status_scroll_layout.itemAt(i).widget().deleteLater()
        self.user_status_scrollArea_mutex.unlock()
        

    def showDialog(self,msg):
        dlg=dialogWindow(msg)
        dlg.setWindowTitle('chat windodw dialog')
        dlg.exec()

    def changeConnectionSocket(self,conn_socket):
        self.conn_socket=conn_socket

    def fileReceive(self,button,layout,progressBar_layout,file_name,from_name,file_id):
        button.setDisabled(True) # disable download button
        dir_path=QFileDialog.getExistingDirectory(self, 'Select Folder', './')
        if not dir_path:
            button.setEnabled(True) # enable download button
            return
        print(f'foldername: {dir_path}')

        #widget handling
        if progressBar_layout.count()>1:
            progressBar_layout.itemAt(1).widget().deleteLater()
            progressBar= progressBar_layout.itemAt(0).widget()
            progressBar.setValue(0)
            progressBar.setVisible(True)

        #make file path
        real_file_name=time.strftime('%Y%m%d%H%M%S',time.gmtime())+ \
                        '_'+from_name+ \
                        '_'+file_name
        file_path_real_name=''
        if dir_path.find('/')>=0:
            file_path_real_name= '/'.join((dir_path,real_file_name))
        else:
            file_path_real_name= os.path.join(dir_path,real_file_name)
        
        file_thread=fileTransferWorker(self,file_path_real_name,self.server_address[0],self.file_server_port_and_key[0],\
                                       self.file_server_port_and_key[1], self.server_pw_client_name[1],self.server_thread_id, \
                                       layout,progressBar_layout,True,button,file_id)
        file_thread.progressSignal.connect(self.handleProgress)
        file_thread.resultSignal.connect(self.handleResult)
        file_thread.start()
        self.tmp_file_thread_list_mutex.lock()
        self.tmp_file_thread_list.append(file_thread)
        self.tmp_file_thread_list_mutex.unlock()

    def fileTransfer(self):
        fname=QFileDialog.getOpenFileName(self, 'Open file', './')
        if not fname[0]:
            return
        print(f'filename: {os.path.split(fname[0])[1]}')

        layout,progressBar_layout= self.displayMSGToWidget(os.path.split(fname[0])[1],'',False,True)

        file_thread=fileTransferWorker(self,fname[0],self.server_address[0],self.file_server_port_and_key[0],\
                                       self.file_server_port_and_key[1], self.server_pw_client_name[1],self.server_thread_id, \
                                       layout,progressBar_layout)
        file_thread.progressSignal.connect(self.handleProgress)
        file_thread.resultSignal.connect(self.handleResult)
        file_thread.start()
        self.tmp_file_thread_list_mutex.lock()
        self.tmp_file_thread_list.append(file_thread)
        self.tmp_file_thread_list_mutex.unlock()

    def handleProgress(self,progress_data):
        progress_data['progress_bar_layout'].itemAt(0).widget().show()
        progress_data['progress_bar_layout'].itemAt(0).widget().setValue(int(progress_data['progress_rate']*100))

    def handleResult(self,result_data):
        if result_data['type']=='upload':
            result_data['progress_bar_layout'].itemAt(0).widget().deleteLater()
        else:
            result_data['progress_bar_layout'].itemAt(0).widget().setVisible(False)
            
        label=QLabel('')
        if result_data['success']:
            label.setText('file '+result_data['type']+' succeeded')
            label.setStyleSheet("""
                    color: blue
                """)
        else:
            label.setText('file '+result_data['type']+' failed')
            label.setStyleSheet("""
                    color: red
                """)
        result_data['progress_bar_layout'].addWidget(label)

        if result_data['type']=='download':
            result_data['download_button'].setEnabled(True)


    def safeRemoveTmpWorker(self,target_thread):
        #append thread to thread collector's list
        self.file_thread_collector_thread.appendThread(target_thread)
        #remove thread from tmp thread list
        self.tmp_file_thread_list_mutex.lock()
        for i in range(len(self.tmp_file_thread_list)):
            thread=self.tmp_file_thread_list[i]
            if target_thread is thread:
                self.tmp_file_thread_list.pop(i)
                break
        self.tmp_file_thread_list_mutex.unlock()

    def closeAllSocket(self):
        try:
            if self.conn_socket.fileno()>=0:
                self.conn_socket.close()
        except socket.error as e:
            pass

def myExceptionHook(exctype,value,traceback):
    print(exctype,value,traceback)

    sys._excepthook(exctype,value,traceback)

if __name__=='__main__':
    sys._excepthook = sys.excepthook
    sys.excepthook = myExceptionHook
    
    app= QApplication(sys.argv)
##    window= chatBoxWindow()
    login_window= loginWindow()
    while True:
        login_window.show()
        app.exec_()
        if login_window.open_chat_window:
            chat_window=chatBoxWindow(login_window.conn_socket, \
                                      (login_window.serverIP,login_window.serverPort) ,\
                                      (login_window.pw, login_window.name), \
                                      (login_window.file_server_port,login_window.file_transfer_key),\
                                      login_window.server_thread_id)
            chat_window.show()
            app.exec()
            print('main bp')
        else:
            break
        login_window.open_chat_window=False
        keep_running[0]=True
