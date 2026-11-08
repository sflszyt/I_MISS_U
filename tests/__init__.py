"""Test fixtures always use a synthetic identity, never machine-private defaults."""
import os

os.environ['IMISSU_OWNER_ID'] = 'owner'
