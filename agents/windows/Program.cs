using System;
using System.Linq;
using System.Net;
using System.Text;
using System.Timers;
using System.Net.NetworkInformation;
using System.Collections.Generic;
using System.Configuration;
using System.Runtime.Versioning;
using System.Web.Script.Serialization;

namespace AssetAgent
{
    class Program
    {
        static Timer timer;
        static string ApiUrl = ConfigurationManager.AppSettings["ApiUrl"];
        static string AgentToken = ConfigurationManager.AppSettings["AgentToken"];
        static int IntervalSeconds = int.Parse(ConfigurationManager.AppSettings["IntervalSeconds"] ?? "60");

        static void Main(string[] args)
        {
            timer = new Timer(IntervalSeconds * 1000);
            timer.Elapsed += (s,e)=> Send();
            timer.AutoReset = true;
            timer.Enabled = true;
            Send();
            System.Threading.Thread.Sleep(System.Threading.Timeout.Infinite);
        }

        static string GetMac()
        {
            foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
            {
                var addr = nic.GetPhysicalAddress();
                if (addr != null && addr.ToString().Length == 12)
                {
                    return string.Join(":", Enumerable.Range(0,6).Select(i => addr.ToString().Substring(i*2,2)));
                }
            }
            return null;
        }

        static List<string> GetIPs()
        {
            var ips = new List<string>();
            foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
            foreach (var ua in ni.GetIPProperties().UnicastAddresses)
                ips.Add(ua.Address.ToString());
            return ips.Distinct().ToList();
        }

        static object Collect()
        {
            return new {
                name = Environment.MachineName,
                type = "workstation",
                mac = GetMac(),
                ips = GetIPs(),
                attributes = new {
                    os = new {
                        family = "windows",
                        version = Environment.OSVersion.VersionString
                    }
                }
            };
        }

        static void Send()
        {
            try
            {
                var payload = new {
                    asset = Collect(),
                    online_status = true
                };
                var json = new JavaScriptSerializer().Serialize(payload);
                var data = Encoding.UTF8.GetBytes(json);
                var req = (HttpWebRequest)WebRequest.Create(ApiUrl);
                req.Method = "POST";
                req.ContentType = "application/json";
                req.Headers.Add("X-Agent-Token", AgentToken);
                using (var stream = req.GetRequestStream())
                    stream.Write(data, 0, data.Length);
                var resp = (HttpWebResponse)req.GetResponse();
                resp.Close();
            }
            catch {}
        }
    }
}
