# Corporate VPN Configuration with GlobalProtect

- **Document ID**: `IT-02`
- **Domain**: IT Support
- **Category**: Network & Remote Access
- **Keywords**: vpn, globalprotect, remote access, vpn connection error, split tunneling

## Policy & Procedure Details
Remote employees must connect to the corporate network using Palo Alto GlobalProtect VPN. To install or configure: 1. Launch the GlobalProtect agent from your system tray or application folder. 2. Enter portal address 'vpn.novatech.com'. 3. Authenticate using your NovaTech Single Sign-On (SSO) credentials followed by Duo MFA push. GlobalProtect operates with split-tunneling enabled by default; corporate internal resources (staging, Jira, internal wikis) are routed through the VPN tunnel, while public internet traffic (Zoom, YouTube, web browsing) bypasses it. If you receive error 'Gateway Not Reachable', verify your local internet connection, restart the GlobalProtect service, and verify that port 443/IPSec is not blocked by your ISP.

## Frequently Asked Questions
- *How do I connect to the VPN?*
- *How do I connect to the corporate VPN?*
- *What is the GlobalProtect portal address?*
- *Why is my GlobalProtect VPN giving 'Gateway Not Reachable'?*
