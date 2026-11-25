# Mobile Device Management (MDM) with Jamf and Microsoft Intune

- **Document ID**: `IT-14`
- **Domain**: IT Support
- **Category**: Device Management
- **Keywords**: jamf, intune, mdm profile, device compliance

## Policy & Procedure Details
All company-owned macOS devices are managed via Jamf Pro, and Windows devices via Microsoft Intune. MDM automatically pushes operating system security patches, disk encryption (FileVault / BitLocker), and anti-malware signatures (CrowdStrike Falcon). Employees are notified 7 days prior to mandatory OS updates and can defer restarts up to 3 times before an automated update occurs. Do not attempt to remove or disable the MDM configuration profile, as this will revoke access to corporate SSO and VPN.

## Frequently Asked Questions
- *What MDM software does NovaTech use?*
- *Can I defer operating system updates on my work laptop?*
- *What happens if I remove the Jamf profile?*
