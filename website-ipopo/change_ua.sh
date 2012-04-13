#!/bin/sh

LAYOUT="./source/_templates/layout.html"

if [ "$1" = "set" ]
then
	sed -i 's/UA-XXXXXXXX-X/'$2'/g' $LAYOUT

elif [ "$1" = "reset" ]
then
	sed -i 's/UA-[0-9]*-[0-9]/UA-XXXXXXXX-X/g' $LAYOUT

else
	echo "Usage: $0 [set <ID> | reset]"
fi

