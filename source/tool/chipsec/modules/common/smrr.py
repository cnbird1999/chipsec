#CHIPSEC: Platform Security Assessment Framework
#Copyright (c) 2010-2015, Intel Corporation
# 
#This program is free software; you can redistribute it and/or
#modify it under the terms of the GNU General Public License
#as published by the Free Software Foundation; Version 2.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with this program; if not, write to the Free Software
#Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
#Contact information:
#chipsec@intel.com
#




## \addtogroup modules
# __chipsec/modules/common/smrr.py__ - checks for SMRR configuration to protect from SMRAM cache attack
#


from chipsec.module_common import *
from chipsec.hal.msr import *

TAGS = [MTAG_BIOS,MTAG_SMM]

class smrr(BaseModule):

    def __init__(self):
        BaseModule.__init__(self)

    def is_supported(self):
        return True

    #
    # Check that SMRR are supported by CPU in IA32_MTRRCAP_MSR[SMRR]
    #
    def check_SMRR_supported(self):
        mtrrcap_msr_reg = chipsec.chipset.read_register( self.cs, 'MTRRCAP' )
        if self.logger.VERBOSE: chipsec.chipset.print_register( self.cs, 'MTRRCAP', mtrrcap_msr_reg )
        smrr = chipsec.chipset.get_register_field( self.cs, 'MTRRCAP', mtrrcap_msr_reg, 'SMRR' )
        return (1 == smrr)

    def check_SMRR(self):
        self.logger.start_test( "CPU SMM Cache Poisoning / System Management Range Registers" )

        if not chipsec.chipset.is_register_defined( self.cs, 'MTRRCAP' ) or \
           not chipsec.chipset.is_register_defined( self.cs, 'IA32_SMRR_PHYSBASE' ) or \
           not chipsec.chipset.is_register_defined( self.cs, 'IA32_SMRR_PHYSMASK' ):
            self.logger.error( "Couldn't find definition of required configuration registers" )
            return ModuleResult.ERROR

        if self.check_SMRR_supported():
            self.logger.log_good( "OK. SMRR range protection is supported" )
        else:
            self.logger.log_important( "CPU does not support SMRR range protection of SMRAM" )
            self.logger.log_skipped_check("CPU does not support SMRR range protection of SMRAM")
            return ModuleResult.SKIPPED

        #
        # SMRR are supported
        #
        smrr_ok = True

        #
        # 2. Check SMRR_BASE is programmed correctly (on CPU0)
        #
        self.logger.log( '' )
        self.logger.log( "[*] Checking SMRR range base programming.." )
        msr_smrrbase = chipsec.chipset.read_register( self.cs, 'IA32_SMRR_PHYSBASE' )
        chipsec.chipset.print_register( self.cs, 'IA32_SMRR_PHYSBASE', msr_smrrbase )
        smrrbase = chipsec.chipset.get_register_field( self.cs, 'IA32_SMRR_PHYSBASE', msr_smrrbase, 'PhysBase', True )
        smrrtype = chipsec.chipset.get_register_field( self.cs, 'IA32_SMRR_PHYSBASE', msr_smrrbase, 'Type' )
        self.logger.log( "[*] SMRR range base: 0x%016X" % smrrbase )

        if smrrtype in self.cs.Cfg.MemType:
            self.logger.log( "[*] SMRR range memory type is %s" % self.cs.Cfg.MemType[smrrtype] )
        else:
            smrr_ok = False
            self.logger.log_bad( "SMRR range memory type 0x%X is invalid" % smrrtype )

        if ( 0 == smrrbase ):
            smrr_ok = False
            self.logger.log_bad( "SMRR range base is not programmed" )

        if smrr_ok: self.logger.log_good( "OK so far. SMRR range base is programmed" )

        #
        # 3. Check SMRR_MASK is programmed and SMRR are enabled (on CPU0)
        #
        self.logger.log( '' )
        self.logger.log( "[*] Checking SMRR range mask programming.." )
        msr_smrrmask = chipsec.chipset.read_register( self.cs, 'IA32_SMRR_PHYSMASK' )
        chipsec.chipset.print_register( self.cs, 'IA32_SMRR_PHYSMASK', msr_smrrmask )
        smrrmask  = chipsec.chipset.get_register_field( self.cs, 'IA32_SMRR_PHYSMASK', msr_smrrmask, 'PhysMask', True )
        smrrvalid = chipsec.chipset.get_register_field( self.cs, 'IA32_SMRR_PHYSMASK', msr_smrrmask, 'Valid' )
        self.logger.log( "[*] SMRR range mask: 0x%016X" % smrrmask )

        if not ( smrrvalid and (0 != smrrmask) ):
            smrr_ok = False
            self.logger.log_bad( "SMRR range is not enabled" )

        if smrr_ok: self.logger.log_good( "OK so far. SMRR range is enabled" )

        #
        # 4. Verify that SMRR_BASE/MASK MSRs have the same values on all logical CPUs
        #
        self.logger.log( '' )
        self.logger.log( "[*] Verifying that SMRR range base & mask are the same on all logical CPUs.." )
        for tid in range(self.cs.msr.get_cpu_thread_count()):
            msr_base = chipsec.chipset.read_register( self.cs, 'IA32_SMRR_PHYSBASE', tid )
            msr_mask = chipsec.chipset.read_register( self.cs, 'IA32_SMRR_PHYSMASK', tid)
            self.logger.log( "[CPU%d] SMRR_PHYSBASE = %016X, SMRR_PHYSMASK = %016X"% (tid, msr_base, msr_mask) )
            if (msr_base != msr_smrrbase) or (msr_mask != msr_smrrmask):
                smrr_ok = False
                self.logger.log_bad( "SMRR range base/mask do not match on all logical CPUs" )
                break

        if smrr_ok: self.logger.log_good( "OK so far. SMRR range base/mask match on all logical CPUs" )

        """
        Don't want invasive action in this test
        
        #
        # 5. Reading from & writing to SMRR_BASE physical address
        # writes should be dropped, reads should return all F's
        #
        self.logger.log( "[*] Trying to read/modify memory at SMRR_BASE address 0x%08X.." % smrrbase )
        smram_buf = self.cs.mem.read_physical_mem( smrrbase, 0x10 )
        #self.logger.log( "Contents at 0x%08X:\n%s" % (smrrbase, repr(smram_buf.raw)) )
        self.cs.mem.write_physical_mem_dword( smrrbase, 0x90909090 )
        if ( 0xFFFFFFFF == self.cs.mem.read_physical_mem_dword( smrrbase ) ):
            self.logger.log_good( "OK. Memory at SMRR_BASE contains all F's and is not modifiable" )
        else:
            smrr_ok = False
            self.logger.log_bad( "Contents of memory at SMRR_BASE are modifiable" )
        """


        self.logger.log( '' )
        if not smrr_ok: self.logger.log_failed_check( "SMRR protection against cache attack is not configured properly" )
        else:           self.logger.log_passed_check( "SMRR protection against cache attack is properly configured" )

        return smrr_ok

    # --------------------------------------------------------------------------
    # run( module_argv )
    # Required function: run here all tests from this module
    # --------------------------------------------------------------------------
    def run( self, module_argv ):
        return self.check_SMRR()
