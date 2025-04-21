#/bin/sh

script_dir=$(dirname "$(readlink -f "$0")")

while true
do
    docker compose -f "$script_dir/../compose.yaml" exec xmpp /bin/sh /opt/register_users.sh
    if [ $? -ne 0 ]
    then
        sleep 1
        echo "Waiting for users to be registered..."
    else
        break
    fi
done
