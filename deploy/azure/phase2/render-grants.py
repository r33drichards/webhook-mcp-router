#!/usr/bin/env python3
"""Render only. IDs must be verified managed identity CLIENT IDs, not principal/object IDs."""
import argparse, uuid
p=argparse.ArgumentParser()
for role in ('reader','control','delivery'): p.add_argument('--'+role,required=True,type=uuid.UUID)
a=p.parse_args()
print('SET XACT_ABORT ON; BEGIN TRANSACTION;')
for role,oid in [('reader',a.reader),('control',a.control),('delivery',a.delivery)]:
 name='router_'+role; sid='0x'+oid.bytes_le.hex()
 print(f"IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name=N'{name}' AND (sid<>{sid} OR type<>'E')) THROW 51000,'Existing principal mismatch',1;")
 print(f"IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name=N'{name}') CREATE USER [{name}] WITH SID={sid}, TYPE=E;")
 print(f'GRANT CONNECT TO [{name}];')
for table in ('Subscriptions','Policies'):
 print(f'GRANT SELECT ON OBJECT::registry.{table} TO [router_reader];')
 print(f'DENY INSERT,UPDATE,DELETE ON OBJECT::registry.{table} TO [router_reader];')
 print(f'GRANT SELECT,INSERT,UPDATE,DELETE ON OBJECT::registry.{table} TO [router_control];')
 print(f'DENY INSERT,UPDATE,DELETE ON OBJECT::registry.{table} TO [router_delivery];')
print('GRANT SELECT ON OBJECT::delivery.RequestLog TO [router_control];')
for table,permissions in [('Receipts','SELECT,INSERT'),('Outbox','SELECT,INSERT,UPDATE'),('RequestLog','SELECT,INSERT,DELETE')]:
 print(f'GRANT {permissions} ON OBJECT::delivery.{table} TO [router_delivery];')
print('COMMIT;')
