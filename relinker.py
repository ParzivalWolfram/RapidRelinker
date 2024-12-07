#Rapid Relinker (working title)
#by Parzival Wolfram (parzivalwolfram@gmail.com)
#MIT license


import os
from time import time
from numpy import uint8, int8, uint16, int16, uint32, int32
from sys import argv

#VRC4 memory region addresses as example,
#change as needed
memory_regions = {
        "REGION_SRAM": 0x6000,
        "REGION_RESERVED_MEMORY": 0x6200,
        "REGION_MAP_DECOMPRESSION_BUFFER": 0x6400,
        "REGION_BANKED_ROM": 0x8000,
        "REGION_STATIC_ROM": 0xC000,
        "NMI": 0xFFFA,
        "START": 0xFFFC,
        "BRK": 0xFFFE
        }

DataBusSize = 0 #used for extended reference features, shouldn't matter a ton unless you need SPECIFICALLY upper/lower bytes or whatever

little_endian = True

debug = False

class File:
        name = ""
        needs = []
        alreadyProcessed = False
        SymbolTable = []
        reparse = False
        def __init__(self,name,needs):
                self.name = name
                self.needs = needs
                self.alreadyProcessed = False
                self.SymbolTable = []
                self.reparse = False

class Symbol:
        code = []
        address = None
        refs = []
        name = ""
        length = 0
        alreadyLinked = False
        similarTo = []
        ignoreDupes = False
        def __init__(self,code,refs,name,address=None,ignoreDupes=False):
                if debug:
                        print("New symbol: "+str(name))
                self.code = code
                self.address = address
                self.refs = refs
                self.name = name
                self.length = len(code)
                self.alreadyLinked = False
                self.similarTo = []
                self.ignoreDupes = ignoreDupes
        def __lt__(self,other):
                return self.address < other.address

class Reference:
        parent = None
        link = ""
        position = 0
        width = 0
        address = None
        offset = 0
        byteSplit = 0
        def __init__(self, link, position, width, offset = 0, byteSplit = -1):
                if debug:
                        print("New reference to: "+str(link))
                self.parent = None
                self.link = link
                self.position = position
                self.width = width
                self.address = None
                self.offset = offset
                self.byteSplit = byteSplit

#standard blob of os.walk helpers
def recursive(pathIn):
	return [os.path.join(root, name) for root, dirs, files in os.walk(pathIn) for name in files] #walks the entire folder tree from current dir downward, returns list of file paths
def standard(pathIn):
	return [f for f in os.listdir(pathIn) if os.path.isfile(f)] #returns list of files in current folder only

#parse lines as needed
def getObjLineSymbol(lineIn):
        return str(lineIn.split("(")[0])
def getObjLineBody(lineIn):
        return str(lineIn.split("(")[1].split(")")[0]).split(" ")

#check for duped symbol name
def checkSymbolName(name,fileIn):
        for i in fileIn.SymbolTable:
                if name == i.name:
                        return False
        return True

#parse code struct, check for refs
def parseCodeStruct(bufferIn):
        loopnum = 0
        code_buffer = []
        ref_buffer = []
        while loopnum < len(bufferIn):
                currentSplit = str(bufferIn[loopnum])
                if len(currentSplit) == 2:
                        code_buffer.append(str(currentSplit))
                else:
                        tempref = []
                        tempoffset = 0
                        currentReference = currentSplit.split(",")
                        if len(currentReference) <= 1:
                                print("ERROR: Malformed reference to "+str(currentReference[0])+"!\nData received from parser was:\n\n"+str(bufferIn))
                                exit(1)
                        if "+" in currentReference[0]:
                                tempref.append(str(currentReference[0]).split("+")[0])
                                tempoffset = int(str(currentReference[0]).split("+")[1],16)
                        else:
                                tempref.append(str(currentReference[0]))
                                tempoffset = 0
                        tempref.append(len(code_buffer))
                        if "/" in currentReference[1]:
                                tempbuf = currentReference[1].split("/")
                                tempref.append(int(tempbuf[0]))
                                tempref.append(int(tempbuf[1]))
                        else:
                                tempref.append(int(currentReference[1]))
                                tempref.append(int(-1))
                        ref_buffer.append(Reference(link = tempref[0],position = tempref[1],width = tempref[2],offset = tempoffset,byteSplit = tempref[3]))
                        if tempref[3] == -1:
                                if debug:
                                        print("SUPERDEBUG: "+str(currentReference[0])+" is normal pointer. Pointer type: "+str(currentReference[1]))
                                tempcount = 0
                                for i in range(int(tempref[2])):
                                        tempcount += 1
                                        code_buffer.append("00")
                                if debug:
                                        print("SUPERDEBUG: tempcount for pointer: "+str(tempcount))
                        else:
                                if debug:
                                        print("SUPERDEBUG: "+str(currentReference[0])+" is split pointer. Pointer type: "+str(currentReference[1]))
                                code_buffer.append("00")#we only need one since we only support one byte in a split pointer at current
                loopnum += 1
        return code_buffer, ref_buffer

#big-ass state machine incoming
def parseObjFile(listIn,fileIn):
        SymbolTable = fileIn.SymbolTable
        global DataBusSize
        currentAddress = -1
        neededFiles = []
        for i in listIn:
                if "(" in i and i.strip("\r").strip("\n") != "" and i[0] != ";":
                        if getObjLineSymbol(i) == "ORG":
                                currentAddress = getObjLineBody(i)[0]
                                if currentAddress in list(memory_regions.keys()):
                                        currentAddress = memory_regions[currentAddress]
                                else:
                                        currentAddress = int(currentAddress, base = 16)
                        elif getObjLineSymbol(i) == "DEF":
                                newDefinition = getObjLineBody(i)[0].split(",")
                                if checkSymbolName(str(newDefinition[0]),fileIn):
                                        SymbolTable.append(Symbol([],[],str(newDefinition[0]),int(newDefinition[1],base=16),ignoreDupes = True))
                                else:
                                        print("ERROR: Symbol name conflict: "+str(newDefinition[0]))
                                        exit(1)
                        elif getObjLineSymbol(i) == "BIT":
                                try:
                                        DataBusSize = int(getObjLineBody(i)[0])
                                except ValueError:
                                        print("ERROR: Invalid data bus length!")
                                        exit(1)
                        elif getObjLineSymbol(i) == "INCLUDE":
                                if fileIn.reparse == False:
                                        try:
                                                neededFiles.append(File(str(getObjLineBody(i)[0]),[]))
                                        except:
                                                print("Malformed INCLUDE statement!")
                                                exit(1)
                        else:
                                currentName = getObjLineSymbol(i)
                                if checkSymbolName(currentName,fileIn):
                                        code_result, ref_result = parseCodeStruct(getObjLineBody(i))
                                        for ref in ref_result:
                                                ref.parent = currentName
                                        if currentAddress != -1:
                                                SymbolTable.append(Symbol(code_result,ref_result,currentName,currentAddress,ignoreDupes = ("ignore-dupe" in i))) #i can't believe that fucking works
                                                currentAddress += len(code_result)
                                        else:
                                                SymbolTable.append(Symbol(code_result,ref_result,currentName))
                                else:
                                        print("ERROR: Symbol name conflict: "+str(currentName))
                                        exit(1)
        if len(neededFiles) > 0:
                return neededFiles
        return False

#fixup references
def fixReferences(fileIn):
        for i in fileIn.SymbolTable:
                for j in i.refs:
                        result = findSymbolByName(j.link,fileIn)
                        if result != -1:
                                j.address = fileIn.SymbolTable[result].address
                        else:
                                print("Unresolved symbol: "+str(j.link))
                                exit(1)

#naive code duplication check
def checkSymDupes(fileIn):
        for i in fileIn.SymbolTable:
                for j in fileIn.SymbolTable:
                        #if names are not the same (prevents matching to self)
                        #and code segments are the same (reference addresses are 00h filled at this point)
                        #and the length of the code segment is more than a single jump instruction (typically >=3 bytes)
                        #and they've not already been spotted
                        #AND they don't have an ignore-dupe flag in a comment
                        if i.name != j.name and i.code == j.code and len(i.code) > 3 and len(j.code) > 3 and i.name not in j.similarTo and (not i.ignoreDupes and not j.ignoreDupes):
                                print("WARNING: Symbols "+str(i.name)+" and "+str(j.name)+" may be the same data! Consider deduplicating.")
                                i.similarTo.append(j.name)
                                j.similarTo.append(i.name)

#find a symbol by name or reference, return its index into SymbolTable
def findSymbolByName(symbolName,fileIn):
        for i in fileIn.SymbolTable:
                if i.name == symbolName:
                        return fileIn.SymbolTable.index(i)
        return -1
def findSymbolByReference(refIn,fileIn):
        return findSymbolByName(refIn.parent,fileIn)

#we have to sort manually due to these being objects,
#and because if we don't they're emitted in the wrong fucking order.
def sortSymbols(fileIn):
        sortedSymbolTable = sorted(fileIn.SymbolTable)        
        if len(fileIn.SymbolTable) != len(sortedSymbolTable):
                print("ERROR: Symbol sorting lost entries!")
                print("Unsorted entries: "+str(len(fileIn.SymbolTable)))
                print("Sorted entries: "+str(len(sortedSymbolTable)))
                print("Lost entries:")
                for i in fileIn.SymbolTable:
                        if i not in sortedSymbolTable:
                                print("\t- "+str(i.name))
                exit(1)
        fileIn.SymbolTable = sortedSymbolTable
        return sortedSymbolTable

#handle relinking
def buildDataBlob(fileIn):
        tempbuf = []
        for i in fileIn.SymbolTable:
                if i.refs != [] and not i.alreadyLinked:
                        codebuf = i.code
                        for j in i.refs:
                                if debug:
                                        print("SUPERDEBUG: j.link="+str(j.link)+";i.address+j.position="+hex(i.address+j.position)+";j.address="+str(hex(j.address))+";j.width="+str(j.width))
                                if int(j.width) == 1:
                                        if debug:
                                                print("SUPERDEBUG: Relative pointer detected.")
                                        result = getIndirectRefPointer(i.address,j,fileIn)
                                else:
                                        if debug:
                                                print("SUPERDEBUG: Absolute pointer detected.")
                                        result = getAbsoluteRefPointer(j,fileIn)
                                loopnum = 0
                                while j.position + loopnum < j.position + len(result):
                                        codebuf[loopnum + j.position] = result[loopnum]
                                        loopnum += 1
                        for j in codebuf:
                                tempbuf.append(j)
                        i.alreadyLinked = True
                elif not i.alreadyLinked:
                        for j in i.code:
                                tempbuf.append(j)
                        i.alreadyLinked = True
        return tempbuf

def buildDEFList(fileIn):
        tempbuf = []
        for i in fileIn.SymbolTable:
                tempbuf.append("DEF("+str(i.name)+","+str(hex(i.address)[2:])+")\n")
        return tempbuf

#build pointer bytes from ref
def getAbsoluteRefPointer(refIn,fileIn):
        tempbuf = str('{0:0{1}X}'.format(refIn.address + refIn.offset,refIn.width*2)) #remove "0x" since we're operating on a string here, also https://stackoverflow.com/a/12638477
        tempbuf = [ str(tempbuf[i:i+2]) for i in range(0, refIn.width*2, 2) ] #https://stackoverflow.com/a/13673133

        #sanity check
##        if debug: #plot twist: the sanity check doesn't work. how did i mess this up.
##                if int("".join(tempbuf),16) != int(refIn.address):
##                        print("ERROR: Absolute pointer sanity check failed!")
##                        print("DEBUG: \n\trefIn.address = "+hex(refIn.address)+"\n\ttempbuf = "+str(tempbuf)+"\t/\t"+str(int("".join(tempbuf),16))+"\n\trefIn.width = "+str(refIn.width)+"\n\trefIn.link = "+str(refIn.link)+"\n\tActual difference: "+str(int("".join(tempbuf),16) - int(refIn.address)))
##                        exit(1)        
        if little_endian:
                tempbuf = list(reversed(tempbuf))
        if refIn.byteSplit != -1:
                tempbuf = [tempbuf[refIn.byteSplit]]
        if debug:
                print("SUPERDEBUG: getAbsoluteRefPointer.tempbuf="+str(tempbuf))
        return tempbuf

def getIndirectRefPointer(parentSymbolAddress,refIn,fileIn): #well shit, it's time
        destSymbolAddress = fileIn.SymbolTable[findSymbolByName(refIn.link,fileIn)].address
        newAddress = int8(destSymbolAddress - (parentSymbolAddress + refIn.position + refIn.offset + 1)) #this took me SO. LONG.
        if newAddress > 127 or newAddress < -128:
                print("ERROR: Indirect reference to symbol "+str(refIn.link)+" too far! \nOriginating symbol: "+str(fileIn.SymbolTable[findSymbolByReference(refIn,fileIn)].name)+"\nReference address: "+str(hex(parentSymbolAddress+refIn.position)[2:])+"\nSymbol address: "+str(hex(refIn.address)[2:])+"\nDifference: "+str(newAddress))
                exit(1)
        result = [str('{0:0{1}X}'.format(uint8(int8(newAddress)),2))]

        #sanity check
        if debug:
                if (int8(int(result[0],16)) + int(destSymbolAddress)) != (int(parentSymbolAddress) + int(refIn.position)):
                        print("ERROR: Relative pointer sanity check failed!")
                        print("DEBUG: \n\tint8(int(result[0],16)) = "+str(int8(int(result[0],16)))+"\n\tresult + destSymbolAddress = "+hex(int(result[0],16)+destSymbolAddress)+"\n\tparentSymbolAddress + refIn.position = "+hex(parentSymbolAddress + refIn.position)+"\n\tActual difference: "+str((int8(int(result[0],16)) + int(destSymbolAddress)) - (int(parentSymbolAddress) + int(refIn.position))))
                        exit(1)
        return result

def processFile(fileIn,neededByFile = False):
        i = fileIn.name
        global SymbolTable
        newFilename = ''.join(i.split(".")[:-1])

        #parse OBJ file
        print("File "+str(i)+": reading symbols table...")
        fileHandle = open(i,"r")
        needsOtherFile = parseObjFile(fileHandle.readlines(),fileIn)
        fileHandle.close()
        if needsOtherFile:
                fileIn.SymbolTable = []
                for j in needsOtherFile:
                        print("File "+str(i)+": parsing include "+str(j.name)+"...")
                        processFile(j,True)
                        for k in j.SymbolTable:
                                fileIn.SymbolTable.append(k)
                fileIn.reparse = True
                print("File "+str(i)+": reparsing with includes.")
                processFile(fileIn)
                return

        #fix references
        print("File "+str(i)+": resolving symbol references...")
        fixReferences(fileIn)

        #check for dupes
        print("File "+str(i)+": checking for duplicated symbols...")
        checkSymDupes(fileIn)

        #sort symbols
        print("File "+str(i)+": sorting symbols...")
        sortSymbols(fileIn)
        
        #build relinked binary
        print("File "+str(i)+": building linked blob...")
        result = buildDataBlob(fileIn)
        fileHandle = open(newFilename+str(".lnk"),"wb+")
        tempbuf = ""
        for j in result:
                tempbuf += str(j)
        fileHandle.write(bytes.fromhex(tempbuf))
        fileHandle.close()
        
        #build DEF export list
        print("File "+str(i)+": making definitions file...")
        fileHandle = open(newFilename+str(".def"),"w")
        for j in buildDEFList(fileIn):
                fileHandle.write(j)
        fileHandle.close()
        
        #clear symbol table for next file
        #if not neededByFile:
                #SymbolTable = []

processFile(File(name = str(argv[-1]),needs = []))
