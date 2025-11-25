# 
# Copyright 2025 EDT&Partners
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 

"""
This is an example of how to use the notification metrics endpoints.
"""

import requests
from datetime import datetime

# Base configuration
BASE_URL = "http://localhost:8000"
API_TOKEN = "your_jwt_token_here"

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

def get_notification_metrics(days=7):
    """
    Get metrics for unread notifications.
    """
    url = f"{BASE_URL}/notifications/metrics/unread-count"
    params = {"days": days}
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        print(f"📊 Notification metrics (last {days} days):")
        print(f"   Total unread: {data['total_unread']}")
        print(f"   By type: {data['by_type']}")
        print(f"   By priority: {data['by_priority']}")
        print(f"   By service: {data['by_service']}")
        
        if data['recent_notifications']:
            print(f"   Recent notifications: {len(data['recent_notifications'])}")
            for notif in data['recent_notifications'][:3]:  # Show only the first 3
                print(f"     - {notif['title']} ({notif['notification_type']})")
        
        return data
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None

def get_notifications_by_type(notification_type="error", days=30):
    """
    Get notifications by specific type.
    """
    url = f"{BASE_URL}/notifications/metrics/by-type"
    params = {
        "notification_type": notification_type,
        "days": days
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        print(f"📋 Notifications of type '{notification_type}' (last {days} days):")
        print(f"   Total: {data['count']}")
        
        if data['notifications']:
            print(f"   Examples:")
            for notif in data['notifications'][:3]:  # Show only the first 3
                print(f"     - {notif['title']}")
                print(f"       Priority: {notif['priority']}")
                print(f"       Service: {notif['service_id']}")
                if notif['actions']:
                    print(f"       Actions: {len(notif['actions'])} buttons")
        
        return data
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None

def get_notifications_by_priority(priority="urgent", days=7):
    """
    Get notifications by specific priority.
    """
    url = f"{BASE_URL}/notifications/metrics/by-priority"
    params = {
        "priority": priority,
        "days": days
    }
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        print(f"🚨 Notifications of priority '{priority}' (last {days} days):")
        print(f"   Total: {data['count']}")
        
        if data['notifications']:
            print(f"   Examples:")
            for notif in data['notifications'][:3]:
                print(f"     - {notif['title']}")
                print(f"       Type: {notif['notification_type']}")
                print(f"       Read: {'Yes' if notif['is_read'] else 'No'}")
        
        return data
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None

def get_notification_statistics(days=30):
    """
    Get general notification statistics.
    """
    url = f"{BASE_URL}/notifications/metrics/statistics"
    params = {"days": days}
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        data = response.json()
        print(f"📈 General statistics (last {days} days):")
        
        summary = data['summary']
        print(f"   Total: {summary['total_notifications']}")
        print(f"   Read: {summary['read_notifications']}")
        print(f"   Unread: {summary['unread_notifications']}")
        print(f"   Expired: {summary['expired_notifications']}")
        print(f"   With actions: {summary['notifications_with_actions']}")
        print(f"   Read rate: {summary['read_rate_percentage']}%")
        
        print(f"\n   By type:")
        for notif_type, stats in data['by_type'].items():
            print(f"     {notif_type}: {stats['total']} (read: {stats['read']}, unread: {stats['unread']})")
        
        print(f"\n   By priority:")
        for priority, stats in data['by_priority'].items():
            print(f"     {priority}: {stats['total']} (read: {stats['read']}, unread: {stats['unread']})")
        
        print(f"\n   Top services:")
        for service in data['top_services'][:5]:  # Show only the top 5
            print(f"     {service['service_id']}: {service['total']} notifications")
        
        print(f"\n   Daily statistics (last 7 days):")
        for day_stats in data['daily_stats']:
            print(f"     {day_stats['date']}: {day_stats['total']} total, {day_stats['unread']} unread")
        
        return data
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None

def cleanup_expired_notifications():
    """
    Delete expired notifications (requires admin permissions).
    """
    url = f"{BASE_URL}/notifications/cleanup/expired"
    
    response = requests.delete(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        print(f"🧹 Cleanup completed:")
        print(f"   {data['message']}")
        print(f"   Deleted: {data['deleted_count']}")
        return data
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return None

def create_dashboard_data():
    """
    Create data for a notification dashboard.
    """
    print("🔍 Collecting data for dashboard...")
    
    # Get basic metrics
    metrics = get_notification_metrics(days=7)
    if not metrics:
        return None
    
    # Get general statistics
    stats = get_notification_statistics(days=30)
    if not stats:
        return None
    
    # Create data structure for dashboard
    dashboard_data = {
        "summary": {
            "unread_count": metrics['total_unread'],
            "read_rate": stats['summary']['read_rate_percentage'],
            "notifications_with_actions": stats['summary']['notifications_with_actions']
        },
        "charts": {
            "by_type": metrics['by_type'],
            "by_priority": metrics['by_priority'],
            "by_service": metrics['by_service'],
            "daily_trend": stats['daily_stats']
        },
        "recent_notifications": metrics['recent_notifications'],
        "alerts": []
    }
    
    # Generate alerts based on metrics
    if metrics['total_unread'] > 20:
        dashboard_data['alerts'].append({
            "type": "warning",
            "message": f"You have {metrics['total_unread']} unread notifications",
            "action": "view_notifications"
        })
    
    if metrics['by_priority'].get('urgent', 0) > 0:
        dashboard_data['alerts'].append({
            "type": "error",
            "message": f"You have {metrics['by_priority']['urgent']} urgent notifications",
            "action": "view_urgent"
        })
    
    if stats['summary']['read_rate_percentage'] < 50:
        dashboard_data['alerts'].append({
            "type": "info",
            "message": "Your read rate is low. Consider reviewing notifications",
            "action": "view_notifications"
        })
    
    print(f"✅ Dashboard created with {len(dashboard_data['alerts'])} alerts")
    return dashboard_data

def monitor_notification_health():
    """
    Monitor the health of the notification system.
    """
    print("🏥 Monitoring notification system health...")
    
    # Get statistics of the last 7 days
    stats = get_notification_statistics(days=7)
    if not stats:
        return False
    
    summary = stats['summary']
    
    # Check health metrics
    health_checks = {
        "total_notifications": summary['total_notifications'] > 0,
        "read_rate": summary['read_rate_percentage'] > 70,
        "expired_notifications": summary['expired_notifications'] < 10,
        "notifications_with_actions": summary['notifications_with_actions'] > 0
    }
    
    print(f"   Total notifications: {'✅' if health_checks['total_notifications'] else '❌'}")
    print(f"   Read rate > 70%: {'✅' if health_checks['read_rate'] else '❌'}")
    print(f"   Expired notifications < 10: {'✅' if health_checks['expired_notifications'] else '❌'}")
    print(f"   Notifications with actions: {'✅' if health_checks['notifications_with_actions'] else '❌'}")
    
    # Calculate health score
    health_score = sum(health_checks.values()) / len(health_checks) * 100
    print(f"   Health score: {health_score:.1f}%")
    
    if health_score >= 75:
        print("   🟢 System healthy")
    elif health_score >= 50:
        print("   🟡 System with warnings")
    else:
        print("   🔴 System needs attention")
    
    return health_score >= 75

def generate_notification_report():
    """
    Generate a complete notification report.
    """
    print("📄 Generating notification report...")
    
    # Get data from different periods
    periods = [7, 30, 90]
    report_data = {}
    
    for days in periods:
        stats = get_notification_statistics(days=days)
        if stats:
            report_data[f"{days}_days"] = {
                "summary": stats['summary'],
                "by_type": stats['by_type'],
                "by_priority": stats['by_priority'],
                "top_services": stats['top_services']
            }
    
    # Generate insights
    insights = []
    
    if report_data.get("7_days"):
        week_stats = report_data["7_days"]["summary"]
        if week_stats['read_rate_percentage'] < 60:
            insights.append("Your weekly read rate is low. Consider reviewing notifications more frequently.")
        
        if week_stats['notifications_with_actions'] > 0:
            insights.append(f"You have {week_stats['notifications_with_actions']} notifications with actions pending.")
    
    if report_data.get("30_days"):
        month_stats = report_data["30_days"]["summary"]
        if month_stats['expired_notifications'] > 20:
            insights.append("There are many expired notifications. Consider cleaning up the system.")
    
    # Create report
    report = {
        "generated_at": datetime.now().isoformat(),
        "periods": report_data,
        "insights": insights,
        "recommendations": [
            "Review urgent notifications first",
            "Mark as read notifications processed",
            "Configure filters to organize notifications better",
            "Consider using action buttons for quick responses"
        ]
    }
    
    print(f"✅ Report generated with {len(insights)} insights")
    return report

# Example of use
if __name__ == "__main__":
    print("🚀 Examples of using notification metrics\n")
    
    # 1. Get basic metrics
    print("1. Basic metrics:")
    get_notification_metrics(days=7)
    print()
    
    # 2. Get notifications by type
    print("2. Notifications by type:")
    get_notifications_by_type("error", days=30)
    print()
    
    # 3. Get notifications by priority
    print("3. Notifications by priority:")
    get_notifications_by_priority("urgent", days=7)
    print()
    
    # 4. Get general statistics
    print("4. General statistics:")
    get_notification_statistics(days=30)
    print()
    
    # 5. Create data for dashboard
    print("5. Data for dashboard:")
    dashboard_data = create_dashboard_data()
    if dashboard_data:
        print(f"   Alerts generated: {len(dashboard_data['alerts'])}")
    print()
    
    # 6. Monitor system health
    print("6. Monitor system health:")
    monitor_notification_health()
    print()
    
    # 7. Generate report
    print("7. Complete report:")
    report = generate_notification_report()
    if report:
        print(f"   Insights generated: {len(report['insights'])}")
    
    print("\n✨ Examples completed!") 