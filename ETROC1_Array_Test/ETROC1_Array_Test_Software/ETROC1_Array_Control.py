#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import copy
import time
import visa
import struct
import socket
import winsound
import datetime
import heartrate
from command_interpret import *
from ETROC1_ArrayReg import *
import numpy as np
from command_interpret import *
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.inset_locator import zoomed_inset_axes
from mpl_toolkits.axes_grid1.inset_locator import mark_inset
'''
@author: Wei Zhang
@date: 2018-02-28
This script is used for testing ETROC1 Array chip. The mianly function of this script is I2C write and read, Ethernet communication, instrument control and so on.
'''
hostname = '192.168.2.3'					#FPGA IP address
port = 1024									#port number
#--------------------------------------------------------------------------#
## plot parameters
lw_grid = 0.5                   # grid linewidth
fig_dpi = 800                   # save figure's resolution
#--------------------------------------------------------------------------#
## DDR3 write data to external device
# @param[in] wr_wrap: wrap address
# @param[in] wr_begin_addr: write data begin address
# @param[in] post_trigger_addr: post trigger address
def write_data_into_ddr3(wr_wrap, wr_begin_addr, post_trigger_addr):
    # writing begin address and wrap_around
    val = (wr_wrap << 28) + wr_begin_addr
    cmd_interpret.write_config_reg(8, 0xffff & val)
    cmd_interpret.write_config_reg(9, 0xffff & (val >> 16))
    # post trigger address
    cmd_interpret.write_config_reg(10, 0xffff & post_trigger_addr)
    cmd_interpret.write_config_reg(11, 0xffff & (post_trigger_addr >> 16))
#--------------------------------------------------------------------------#
## DDR3 read data from fifo to ethernet
# @param[in] rd_stop_addr: read data start address
def read_data_from_ddr3(rd_stop_addr):
    cmd_interpret.write_config_reg(12, 0xffff & rd_stop_addr)
    cmd_interpret.write_config_reg(13, 0xffff & (rd_stop_addr >> 16))
    cmd_interpret.write_pulse_reg(0x0020)           # reading start
#--------------------------------------------------------------------------#
## test ddr3
def test_ddr3(data_num):
    cmd_interpret.write_config_reg(0, 0x0000)       # written disable
    cmd_interpret.write_pulse_reg(0x0040)           # reset ddr3 control logic
    time.sleep(0.01)
    cmd_interpret.write_pulse_reg(0x0004)           # reset ddr3 data fifo
    time.sleep(0.01)
    print("sent pulse!")

    cmd_interpret.write_config_reg(0, 0x0001)       # written enable

    write_data_into_ddr3(1, 0x0000000, 0x6000000)   # set write begin address and post trigger address and wrap around
    cmd_interpret.write_pulse_reg(0x0008)           # writing start
    cmd_interpret.write_pulse_reg(0x0010)           # writing stop

    time.sleep(1)
    cmd_interpret.write_config_reg(0, 0x0000)       # write enable
    time.sleep(3)
    read_data_from_ddr3(0x6000000)                  # set read begin address

    data_out = []
    ## memoryview usage
    for i in range(data_num):
        data_out += cmd_interpret.read_data_fifo(50000)           # reading start
    return data_out
#--------------------------------------------------------------------------#
## IIC write slave device
# @param mode[1:0] : '0'is 1 bytes read or wirte, '1' is 2 bytes read or write, '2' is 3 bytes read or write
# @param slave[7:0] : slave device address
# @param wr: 1-bit '0' is write, '1' is read
# @param reg_addr[7:0] : register address
# @param data[7:0] : 8-bit write data
def iic_write(mode, slave_addr, wr, reg_addr, data):
    val = mode << 24 | slave_addr << 17 | wr << 16 | reg_addr << 8 | data
    cmd_interpret.write_config_reg(4, 0xffff & val)
    cmd_interpret.write_config_reg(5, 0xffff & (val>>16))
    time.sleep(0.01)
    cmd_interpret.write_pulse_reg(0x0001)           # reset ddr3 data fifo
    time.sleep(0.01)
    # print(hex(val))
#--------------------------------------------------------------------------#
## IIC read slave device
# @param mode[1:0] : '0'is 1 bytes read or wirte, '1' is 2 bytes read or write, '2' is 3 bytes read or write
# @param slave[7:0]: slave device address
# @param wr: 1-bit '0' is write, '1' is read
# @param reg_addr[7:0] : register address
def iic_read(mode, slave_addr, wr, reg_addr):
    val = mode << 24 | slave_addr << 17 |  0 << 16 | reg_addr << 8 | 0x00	  # write device addr and reg addr
    cmd_interpret.write_config_reg(4, 0xffff & val)
    cmd_interpret.write_config_reg(5, 0xffff & (val>>16))
    time.sleep(0.01)
    cmd_interpret.write_pulse_reg(0x0001)				                      # Sent a pulse to IIC module

    val = mode << 24 | slave_addr << 17 | wr << 16 | reg_addr << 8 | 0x00	  # write device addr and read one byte
    cmd_interpret.write_config_reg(4, 0xffff & val)
    cmd_interpret.write_config_reg(5, 0xffff & (val>>16))
    time.sleep(0.01)
    cmd_interpret.write_pulse_reg(0x0001)				                      # Sent a pulse to IIC module
    time.sleep(0.01)									                      # delay 10ns then to read data
    return cmd_interpret.read_status_reg(0) & 0xff
#--------------------------------------------------------------------------#
## Enable FPGA Descrambler
def Enable_FPGA_Descramblber(val):
    if val==1:
        print("Enable FPGA Descrambler")
    else:
        print("Disable FPGA Descrambler")
    cmd_interpret.write_config_reg(14, 0x0001 & val)       # write enable
#--------------------------------------------------------------------------#
## main functionl
def main():
    slaveA_addr = 0x03                                                  # I2C slave A address
    slaveB_addr = 0x7f                                                  # I2C slave B address

    reg_val = []
    ETROC1_ArrayReg1 = ETROC1_ArrayReg()                                # New a class
    ETROC1_ArrayReg1.set_CLSel(1)
    ETROC1_ArrayReg1.set_RfSel(2)
    ETROC1_ArrayReg1.set_HysSel(0xf)
    ETROC1_ArrayReg1.set_IBSel(7)
    ETROC1_ArrayReg1.set_QSel(2)
    reg_val = ETROC1_ArrayReg1.get_config_vector()                      # Get Array Pixel Register default data

    ## write data to I2C register one by one
    print("Write data into I2C slave:")
    print(reg_val)
    for i in range(len(reg_val)):
        if i < 32:                                                      # I2C slave A write
            iic_write(1, slaveA_addr, 0, i, reg_val[i])
        else:                                                           # I2C slave B write
            iic_write(1, slaveB_addr, 0, i-32, reg_val[i])

    ## read back data from I2C register one by one
    iic_read_val = []
    for i in range(len(reg_val)):
        if i < 32:
            iic_read_val += [iic_read(0, slaveA_addr, 1, i)]            # I2C slave A read
        else:
            iic_read_val += [iic_read(0, slaveB_addr, 1, i-32)]         # I2C slave B read
    print("I2C read back data:")
    print(iic_read_val)

    ## compare I2C write in data with I2C read back data
    if iic_read_val == reg_val:
        print("Wrote in data matches with read back data!")
    else:
        print("Wrote in data doesn't matche with read back data!!!!")
        winsound.Beep(1000, 500)

    ## Receive DMRO output data and store it to dat file
    for k in range(1):
        Board_num = 1
        Total_point = 50000 * 200
        filename = "Array_Data_B%s_%sP.dat"%(Board_num, Total_point)
        print("filename is: %s"%filename)
        print("Fetching NO.%01d file..."%k)
        data_out = [0]
        data_out = test_ddr3(Total_point/50000)                          ## num: The total fetch data num * 50000
        print(data_out)

        ##  Creat a directory named path with date of today
        today = datetime.date.today()
        todaystr = today.isoformat() + "_Array_Test_Result"
        try:
            os.mkdir(todaystr)
            print("Directory %s was created!"%todaystr)
        except FileExistsError:
            print("Directory %s already exists!"%todaystr)

        data_out = [['ffaa55aa']]
        with open("./%s/%s_%01d.dat"%(todaystr, filename, k),'w') as infile:
            for i in range(len(data_out)):
                TDC_data = []
                for j in range(30):
                    TDC_data += [((data_out[i] >> j) & 0x1)]
                hitFlag = TDC_data[29]
                TOT_Code1 = TDC_data[0] << 8 | TDC_data[1] << 7 | TDC_data[2] << 6 | TDC_data[3] << 5 | TDC_data[4] << 4 | TDC_data[5] << 3 | TDC_data[6] << 2 | TDC_data[7] << 1 | TDC_data[8]
                TOA_Code1 = TDC_data[9] << 9 | TDC_data[10] << 8 | TDC_data[11] << 7 | TDC_data[12] << 6 | TDC_data[13] << 5 | TDC_data[14] << 4 | TDC_data[15] << 3 | TDC_data[16] << 2 | TDC_data[17] << 1 | TDC_data[18]
                Cal_Code1 = TDC_data[19] << 9 | TDC_data[20] << 8 | TDC_data[21] << 7 | TDC_data[22] << 6 | TDC_data[23] << 5 | TDC_data[24] << 4 | TDC_data[25] << 3 | TDC_data[26] << 2 | TDC_data[27] << 1 | TDC_data[28]
                # print(TOA_Code1, TOT_Code1, Cal_Code1, hitFlag)
                infile.write("%3d %3d %3d %d\n"%(TOA_Code1, TOT_Code1, Cal_Code1, hitFlag))

#--------------------------------------------------------------------------#
## if statement
if __name__ == "__main__":
    #s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)	#initial socket
	#s.connect((hostname, port))								#connect socket
	#cmd_interpret = command_interpret(s)					#Class instance
	main()													#execute main function
    #s.close()												#close socket
