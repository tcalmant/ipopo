#!/bin/sh

until ejabberdctl status
do
    echo "Waiting for ejabberd to start..."
    sleep 1
done

echo "Register admin"
until ejabberdctl check_account admin localhost
do
    ejabberdctl register admin localhost admin
    if [ $? -ne 0 ]
    then
        echo "Waiting for user admin to be registered..."
        sleep 1
    fi
done
echo "Done registering admin"

echo "Register users"
for user in user1 user2 user3
do
    until ejabberdctl check_account $user localhost
    do
        ejabberdctl register $user localhost foobar
        if [ $? -ne 0 ]
        then
            echo "Waiting for user $user to be registered..."
            sleep 1
        fi
    done
done
echo "Done registering users"
