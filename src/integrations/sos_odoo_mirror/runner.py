"""Explicit mirror run/reconcile/status commands; credentials come from private env."""
import argparse
import asyncio
import json
import logging


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--run',action='store_true')
    action.add_argument('--status',action='store_true')
    action.add_argument('--retry-reviewed-blocked',action='store_true',help='Requeue all blocked deliveries only after reviewing/fixing conflicts and mappings')
    action.add_argument('--replay-reviewed-all',action='store_true',help='Owner-reviewed recovery after restoring Odoo; stop delivery jobs before resetting acknowledgements')
    action.add_argument('--requeue-cutoff-exclusions-from',metavar='YYYY-MM-DD',help='Owner-reviewed backfill: stop delivery, lower the Odoo cutoff, then requeue latest historical exclusion receipts from this date')
    parser.add_argument('--reconcile',action='store_true',help='Force full source scans on an explicit run')
    args=parser.parse_args()
    if args.reconcile and not args.run:parser.error('--reconcile requires --run')
    logging.disable(logging.CRITICAL)
    try:
        from src.core.config import settings
        from .delivery import DeliveryJournal
        if args.run:
            from src.worker.jobs.push_data.sos_odoo_mirror import build_sos_mirror_job
            job=build_sos_mirror_job(settings)
            result=asyncio.run(job.run(reconcile=args.reconcile))
        else:
            if settings.sos_mirror_journal_root is None:raise ValueError('mirror_journal_root_required')
            journal=DeliveryJournal(settings.sos_mirror_journal_root,{
                'url':settings.sos_mirror_odoo_url,'database':settings.sos_mirror_odoo_database,
                'account_code':settings.sos_mirror_account_code,'company_id':settings.sos_mirror_company_id})
            if args.retry_reviewed_blocked:result={'requeued':journal.retry_blocked(),'summary':journal.summary()}
            elif args.replay_reviewed_all:result={'requeued':journal.replay_reviewed_all(),'summary':journal.summary()}
            elif args.requeue_cutoff_exclusions_from:result={'requeued':journal.requeue_cutoff_exclusions(args.requeue_cutoff_exclusions_from),'summary':journal.summary()}
            else:result=journal.summary()
        print(json.dumps(result))
    except Exception:
        parser.exit(1,'mirror_operation_failed; verify source completeness, reviewed mappings, target settings and private journal\n')


if __name__=='__main__':main()
