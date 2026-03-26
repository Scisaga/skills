#!/bin/bash
#
# 一个尽量精简的 AliDNS DDNS 更新脚本。
# 这个脚本早于仓库统一 env 包装模式，因此整体保留原状，
# 主要因为它把 AliDNS 签名流程直接实现到了脚本里。
# 使用前请填写下面的变量，或者复制到私有版本中维护。
set -e

# 阿里云鉴权信息。不要把真实值提交到 git。
aliddns_ak=
aliddns_sk=


# 目标记录：二级域名 + 主域名。
aliddns_subdomain=%40 #'二级域名，%40代表@，aka一级域名'
aliddns_domain= #'mydomain.com'

# 记录类型：A 为 IPv4，AAAA 为 IPv6。
aliddns_iptype=A # 'A' 或 'AAAA'，代表ipv4 和 ipv6

# TTL 默认 10 分钟。
aliddns_ttl=600 #"600"

#--------------------------------------------------------------

machine_ip=""
ddns_ip=""
aliddns_record_id=""

if [ "$aliddns_subdomain" = "@" ]
then
  aliddns_name=$aliddns_domain
else
  aliddns_name=$aliddns_subdomain.$aliddns_domain
fi

now=`date`
echo "**************************************************"
echo "$now"
echo "$aliddns_name"

# 下面几组函数分别负责：
# 1. 获取本机公网 IP
# 2. 读取当前 DNS 解析
# 3. 进行 AliDNS API 签名与调用
function getMachine_IPv4() {
    echo $(/usr/bin/wget -qO- -t1 -T2 http://ip.3322.net)
}

function getMachine_IPv6() {
    ipv6=`ip addr | grep "inet6.*global" | grep -v "deprecated" | awk '{print $2}' | awk -F"/" '{print $1}' | sed -n '1,1p'`
    echo $ipv6
}

function getDDNS_IP() {
    current_ip=`nslookup -query=$aliddns_iptype $aliddns_name | grep "Address" | grep -v "#53" | awk '{print $2}'`
    echo $current_ip
}

function urlencode() {
    # urlencode <string>
    out=""
    while read -n1 c
    do
        case $c in
            [a-zA-Z0-9._-]) out="$out$c" ;;
            *) out="$out`printf '%%%02X' "'$c"`" ;;
        esac
    done
    echo -n $out
}

function enc() {
    echo -n "$1" | urlencode
}

function send_request() {
    local args="AccessKeyId=$aliddns_ak&Action=$1&Format=json&$2&Version=2015-01-09"
    local hash=$(echo -n "GET&%2F&$(enc "$args")" | openssl dgst -sha1 -hmac "$aliddns_sk&" -binary | openssl base64)
    curl -s "http://alidns.aliyuncs.com/?$args&Signature=$(enc "$hash")"
}

function get_recordid() {
    grep -Eo '"RecordId":"[0-9]+"' | cut -d':' -f2 | tr -d '"'
}

function query_recordid() {
    send_request "DescribeSubDomainRecords" "SignatureMethod=HMAC-SHA1&SignatureNonce=$timestamp&SignatureVersion=1.0&SubDomain=$aliddns_name&Timestamp=$timestamp&Type=$aliddns_iptype"
}

function update_record() {
    send_request "UpdateDomainRecord" "RR=$aliddns_subdomain&RecordId=$1&SignatureMethod=HMAC-SHA1&SignatureNonce=$timestamp&SignatureVersion=1.0&TTL=$aliddns_ttl&Timestamp=$timestamp&Type=$aliddns_iptype&Value=$(enc $machine_ip)"
}

function add_record() {
    send_request "AddDomainRecord&DomainName=$aliddns_domain" "RR=$aliddns_subdomain&SignatureMethod=HMAC-SHA1&SignatureNonce=$timestamp&SignatureVersion=1.0&TTL=$aliddns_ttl&Timestamp=$timestamp&Type=$aliddns_iptype&Value=$(enc $machine_ip)"
}

# 根据记录类型获取当前机器应上报的 IP。
if [ "$aliddns_iptype" = 'A' ]
then
    echo "ddns is IPv4."

    machine_ip=`echo "$(getMachine_IPv4)"`
    echo "machine_ip = $machine_ip"

    aliddns_record_id=$aliddnsipv4_record_id
else
    echo "ddns is IPv6."

    machine_ip=`echo "$(getMachine_IPv6)"`
    echo "machine_ip = $machine_ip"

    aliddns_record_id=$aliddnsipv6_record_id
fi

ddns_ip=`echo "$(getDDNS_IP)"`
echo "ddns_ip = $ddns_ip"

# 无法获取本机地址时直接退出，避免把空值写到 DNS。
if [ "$machine_ip" = "" ]
then
    echo "machine_ip is empty!"
    exit 0
fi

# 解析结果与当前公网地址一致时不做更新。
if [ "$machine_ip" = "$ddns_ip" ]
then
    echo "skipping\n"
    exit 1
fi

echo "start update..."

timestamp=`date -u "+%Y-%m-%dT%H%%3A%M%%3A%SZ"`

# 优先查询已有 RecordId，只有没有时才进入新增逻辑。
if [ "$aliddns_record_id" = "" ]
then
    aliddns_record_id=`query_recordid | get_recordid`
    echo "----------------" $aliddns_record_id "\n"

    if [ "$aliddns_iptype" = 'A' ]
    then
        aliddnsipv4_record_id=$aliddns_record_id
    else
        aliddnsipv6_record_id=$aliddns_record_id
    fi
fi

# 兼容 `*` / `@` 这类需要 URL 编码的记录名。
if [ "$aliddns_record_id" = "" ]
then
    echo "add record starting"

    aliddns_record_id=`add_record | get_recordid`

    if [ "$aliddns_record_id" = "" ]
    then
        echo "aliddns_record_id is empty. \n"
    else
        if [ "$aliddns_iptype" = 'A' ]
        then
            aliddnsipv4_record_id=$aliddns_record_id
        else
            aliddnsipv6_record_id=$aliddns_record_id
        fi

        echo "added record $aliddns_record_id \n"
    fi
else
    echo "update record starting"
    update_record $aliddns_record_id
    echo "updated record $aliddns_record_id \n"
fi
