#import "JKObjCExceptions.h"

NSException * _Nullable JKCatchObjCException(NS_NOESCAPE void (^block)(void)) {
    @try {
        block();
        return nil;
    } @catch (NSException *exception) {
        return exception;
    }
}
