from fastapi import APIRouter, BackgroundTasks

# from app.worker.tasks.gmail_download_tasks import GmailTasks
# from app.worker.tasks.report_tasks import SuttonReportTasks
# from app.worker.services.guest_supply_order_service import GuestSupplyPOService

# router = APIRouter(prefix="/admin", tags=["admin"])


# @router.post("/trigger-task/{task_name}")
# async def trigger_task(task_name: str, background_tasks: BackgroundTasks):
#     """Manually trigger a worker task"""

#     gmail_tasks = GmailTasks()
#     guest_po_tasks = GuestSupplyPOService()
#     sutton_report_tasks = SuttonReportTasks()

#     task_map = {
#         "guest_email": gmail_tasks.guest_supply_pdf_download,
#         "guest_process": guest_po_tasks.process_all_guest_supply_pdfs,
#         "sutton_email": gmail_tasks.sutton_report_download,
#         "sutton_process": sutton_report_tasks.process_sutton_reports,
#     }

#     if task_name not in task_map:
#         return {"error": "Invalid task name"}

#     # Run in background
#     background_tasks.add_task(task_map[task_name])

#     return {"message": f"Task '{task_name}' triggered", "status": "running"}
